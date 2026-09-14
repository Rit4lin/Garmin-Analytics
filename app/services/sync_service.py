import logging
import threading
from datetime import date, datetime, timedelta

from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models.all_models import Activity, SyncState
from app.services.activity_service import upsert_activity
from app.services.garmin_client import TOKEN_ERROR, GarminClient, GarminTokenError
from app.services.health_service import (
    upsert_daily,
    upsert_hrv,
    upsert_sleep,
    upsert_training,
    upsert_weights,
)
from app.services.performance_service import (
    upsert_performance_metric,
    upsert_performance_range,
    upsert_personal_records,
)

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = threading.Lock()

    def status(self) -> dict[str, object]:
        with SessionLocal() as db:
            state = db.get(SyncState, "garmin") or SyncState(name="garmin")
            cooldown_seconds = (
                max(0, int((state.next_retry_at - datetime.now()).total_seconds()))
                if state.next_retry_at
                else 0
            )
            return {
                key: getattr(state, key)
                for key in (
                    "status",
                    "progress_current",
                    "progress_total",
                    "last_sync_at",
                    "last_date_downloaded",
                    "error_message",
                    "next_retry_at",
                    "backfill_status",
                    "backfill_cursor_date",
                )
            } | {"cooldown_seconds": cooldown_seconds}

    def request_sync(self) -> bool:
        """Respeta siempre next_retry_at, también para peticiones manuales."""
        if not self._lock.acquire(blocking=False):
            return False
        with SessionLocal() as db:
            state = db.get(SyncState, "garmin")
            if state and state.next_retry_at and state.next_retry_at > datetime.now():
                self._lock.release()
                return False
        threading.Thread(target=self._run, daemon=True, name="garmin-sync").start()
        return True

    def _state(self, db: Session) -> SyncState:
        state = db.get(SyncState, "garmin")
        if state is None:
            state = SyncState(name="garmin")
            db.add(state)
            db.flush()
        return state

    def _plan(self, state: SyncState, today: date) -> tuple[date, date, bool]:
        if state.backfill_status != "completed":
            initial_start = state.backfill_start_date or (
                today - timedelta(days=self.settings.initial_sync_days - 1)
            )
            state.backfill_start_date = initial_start
            start = (
                state.backfill_cursor_date + timedelta(days=1)
                if state.backfill_cursor_date
                else initial_start
            )
            return start, today, True
        return today - timedelta(days=self.settings.sync_recent_days - 1), today, False

    def _run(self) -> None:
        try:
            with SessionLocal() as db:
                state = self._state(db)
                start, end, is_backfill = self._plan(state, date.today())
                if is_backfill:
                    state.backfill_status = "in_progress"
                    state.backfill_started_at = state.backfill_started_at or datetime.now()
                    state.progress_total = (end - state.backfill_start_date).days + 1  # type: ignore[operator]
                    state.progress_current = (start - state.backfill_start_date).days  # type: ignore[operator]
                else:
                    state.progress_current = 0
                    state.progress_total = (end - start).days + 1
                state.status, state.error_message = "running", None
                db.commit()
            if start <= end:
                client = GarminClient(self.settings)
                client.connect()
                self._sync_activities(client, start, end)
                self._sync_days(client, start, end, is_backfill)
                self._sync_performance(client, start, end)
                self._sync_weights(client, start, end)
            with SessionLocal() as db:
                state = self._state(db)
                state.status = "idle"
                state.last_sync_at = datetime.now()
                state.next_retry_at = None
                state.retry_count = 0
                if is_backfill:
                    state.backfill_status = "completed"
                    state.backfill_completed_at = datetime.now()
                state.progress_current = state.progress_total
                db.commit()
        except GarminTokenError:
            self._finish_error(TOKEN_ERROR, retry_seconds=6 * 60 * 60)
        except GarminConnectTooManyRequestsError:
            self._finish_error("Garmin ha limitado las solicitudes (HTTP 429).")
        except GarminConnectConnectionError:
            self._finish_error("Garmin no está disponible temporalmente.", retry_seconds=15 * 60)
        except Exception as exc:
            logger.exception("Sincronización Garmin falló")
            self._finish_error(
                f"Error de sincronización: {type(exc).__name__}", retry_seconds=15 * 60
            )
        finally:
            if self._lock.locked():
                self._lock.release()

    def _finish_error(self, message: str, retry_seconds: int | None = None) -> None:
        with SessionLocal() as db:
            state = self._state(db)
            if retry_seconds is None:
                state.retry_count += 1
                retry_seconds = min(
                    self.settings.garmin_retry_base_seconds * (2 ** (state.retry_count - 1)),
                    8 * 60 * 60,
                )
            state.status, state.error_message = "error", message
            state.next_retry_at = datetime.now() + timedelta(seconds=retry_seconds)
            if state.backfill_status == "in_progress":
                state.backfill_status = "incomplete"
            db.commit()
        logger.warning("%s Reintento permitido en %s s.", message, retry_seconds)

    def _sync_activities(self, client: GarminClient, start: date, end: date) -> None:
        for data in client.activities(start.isoformat(), end.isoformat()):
            with SessionLocal() as db:
                activity_id = str(data.get("activityId"))
                existing = db.get(Activity, activity_id)
                details = splits = None
                if existing is None:
                    details = client.activity_details(activity_id)
                    splits = client.activity_splits(activity_id)
                upsert_activity(db, data, details, splits)
                db.commit()

    def _optional(self, label: str, day: date, operation):  # type: ignore[no-untyped-def]
        try:
            return operation()
        except (GarminConnectTooManyRequestsError, GarminConnectConnectionError):
            raise
        except Exception as exc:
            logger.info("%s no disponible para %s: %s", label, day, type(exc).__name__)
            return None

    def _sync_days(self, client: GarminClient, start: date, end: date, is_backfill: bool) -> None:
        day = start
        while day <= end:
            with SessionLocal() as db:
                stats = client.stats(day.isoformat())
                heart = client.heart_rates(day.isoformat())
                stress = self._optional("Estrés", day, lambda: client.stress(day.isoformat()))
                spo2 = self._optional("SpO2", day, lambda: client.spo2(day.isoformat()))
                respiration = self._optional(
                    "Respiración", day, lambda: client.respiration(day.isoformat())
                )
                battery = self._optional(
                    "Body Battery",
                    day,
                    lambda: client.body_battery(day.isoformat(), day.isoformat()),
                )
                upsert_daily(db, day, stats, heart, stress, spo2, respiration, battery)
                sleep = self._optional("Sueño", day, lambda: client.sleep(day.isoformat()))
                if sleep:
                    upsert_sleep(db, day, sleep)
                hrv = self._optional("HRV", day, lambda: client.hrv(day.isoformat()))
                if hrv:
                    upsert_hrv(db, day, hrv)
                status = (
                    self._optional(
                        "Estado de entrenamiento",
                        day,
                        lambda: client.training_status(day.isoformat()),
                    )
                    or {}
                )
                readiness = (
                    self._optional(
                        "Training readiness",
                        day,
                        lambda: client.training_readiness(day.isoformat()),
                    )
                    or []
                )
                endurance = (
                    self._optional(
                        "Endurance score", day, lambda: client.endurance_score(day.isoformat())
                    )
                    or {}
                )
                hill = (
                    self._optional("Hill score", day, lambda: client.hill_score(day.isoformat()))
                    or {}
                )
                upsert_training(db, day, status, readiness, endurance, hill)
                state = self._state(db)
                state.last_date_downloaded = day
                state.progress_current = (
                    (day - state.backfill_start_date).days + 1
                    if is_backfill and state.backfill_start_date
                    else (day - start).days + 1
                )
                if is_backfill:
                    state.backfill_cursor_date = day
                db.commit()
            day += timedelta(days=1)

    @staticmethod
    def _chunks(start: date, end: date, max_days: int = 365):
        current = start
        while current <= end:
            chunk_end = min(end, current + timedelta(days=max_days - 1))
            yield current, chunk_end
            current = chunk_end + timedelta(days=1)

    def _sync_performance(self, client: GarminClient, start: date, end: date) -> None:
        for chunk_start, chunk_end in self._chunks(start, end):
            race = self._optional(
                "Predicciones de carrera",
                chunk_start,
                lambda: client.race_predictions(
                    chunk_start.isoformat(), chunk_end.isoformat()
                ),
            )
            tolerance = self._optional(
                "Running tolerance",
                chunk_start,
                lambda: client.running_tolerance(
                    chunk_start.isoformat(), chunk_end.isoformat()
                ),
            )
            lactate = self._optional(
                "Histórico de umbral",
                chunk_start,
                lambda: client.lactate_threshold_history(
                    chunk_start.isoformat(), chunk_end.isoformat()
                ),
            )
            with SessionLocal() as db:
                upsert_performance_range(
                    db,
                    chunk_start,
                    chunk_end,
                    race=race,
                    tolerance=tolerance,
                    lactate=lactate,
                )
                db.commit()

        race_latest = self._optional(
            "Predicción de carrera actual",
            end,
            lambda: client.race_predictions(),
        )
        lactate_latest = self._optional(
            "Umbral actual",
            end,
            lambda: client.lactate_threshold(),
        )
        fitness_age = self._optional(
            "Fitness age", end, lambda: client.fitness_age(end.isoformat())
        )
        records = self._optional(
            "Récords personales",
            end,
            lambda: client.personal_records(),
        )
        with SessionLocal() as db:
            upsert_performance_metric(
                db,
                end,
                race=race_latest,
                lactate=lactate_latest,
                fitness_age=fitness_age,
            )
            if records:
                upsert_personal_records(db, records)
            db.commit()

    def _sync_weights(self, client: GarminClient, start: date, end: date) -> None:
        payload = self._optional(
            "Pesos", start, lambda: client.weigh_ins(start.isoformat(), end.isoformat())
        )
        if not payload:
            return
        with SessionLocal() as db:
            upsert_weights(db, payload)
            db.commit()


sync_service = SyncService()
