import logging
import threading
import time
from datetime import date, datetime, timedelta

from garminconnect import GarminConnectTooManyRequestsError
from sqlalchemy import func, select

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

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = threading.Lock()

    def status(self) -> dict[str, object]:
        with SessionLocal() as db:
            state = db.get(SyncState, "garmin") or SyncState(name="garmin")
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
                )
            }

    def request_sync(self, initial: bool = False, force: bool = False) -> bool:
        """Inicia un único trabajo; los botones manuales pueden ignorar la espera."""
        if not self._lock.acquire(blocking=False):
            return False
        if not force:
            with SessionLocal() as db:
                state = db.get(SyncState, "garmin")
                if state and state.next_retry_at and state.next_retry_at > datetime.now():
                    self._lock.release()
                    return False
        thread = threading.Thread(
            target=self._run, args=(initial,), daemon=True, name="garmin-sync"
        )
        thread.start()
        return True

    def _state(self, db):  # type: ignore[no-untyped-def]
        state = db.get(SyncState, "garmin")
        if state is None:
            state = SyncState(name="garmin")
            db.add(state)
            db.flush()
        return state

    def _run(self, initial: bool) -> None:
        try:
            with SessionLocal() as db:
                has_data = db.scalar(select(func.count()).select_from(Activity)) > 0
                state = self._state(db)
                start = date.today() - timedelta(
                    days=self.settings.initial_sync_days
                    if initial or not has_data
                    else self.settings.sync_recent_days
                )
                end = date.today()
                state.status, state.error_message = "running", None
                state.progress_current, state.progress_total = 0, (end - start).days + 1
                db.commit()
            client = GarminClient(self.settings)
            client.connect()
            self._sync_activities(client, start, end)
            self._sync_days(client, start, end)
            self._sync_weights(client, start, end)
            with SessionLocal() as db:
                state = self._state(db)
                state.status, state.last_sync_at, state.last_date_downloaded = (
                    "idle",
                    datetime.now(),
                    end,
                )
                state.progress_current = state.progress_total
                db.commit()
        except GarminTokenError:
            # No reintentamos el token dañado en cada ciclo del scheduler.
            self._finish_error(TOKEN_ERROR, retry_minutes=360)
        except GarminConnectTooManyRequestsError:
            self._finish_error(
                "Garmin ha limitado las solicitudes (HTTP 429). "
                "La sincronización se reintentará más tarde.",
                retry_minutes=60,
            )
        except Exception as exc:
            logger.exception("Sincronización Garmin falló")
            self._finish_error(f"Error de sincronización: {type(exc).__name__}")
        finally:
            self._lock.release()

    def _finish_error(self, message: str, retry_minutes: int | None = None) -> None:
        with SessionLocal() as db:
            state = self._state(db)
            state.status, state.error_message = "error", message
            state.next_retry_at = (
                datetime.now() + timedelta(minutes=retry_minutes) if retry_minutes else None
            )
            db.commit()
        logger.warning(message)

    def _sync_activities(self, client: GarminClient, start: date, end: date) -> None:
        for data in client.activities(start.isoformat(), end.isoformat()):
            with SessionLocal() as db:
                activity_id = str(data.get("activityId"))
                existing = db.get(Activity, activity_id)
                details = splits = None
                if existing is None:  # detalles/splits sólo una vez: evita peticiones repetidas
                    details = client.activity_details(activity_id)
                    time.sleep(self.settings.garmin_request_delay_seconds)
                    splits = client.activity_splits(activity_id)
                upsert_activity(db, data, details, splits)
                db.commit()
            time.sleep(self.settings.garmin_request_delay_seconds)

    def _sync_days(self, client: GarminClient, start: date, end: date) -> None:
        day = start
        while day <= end:
            with SessionLocal() as db:
                stats = client.stats(day.isoformat())
                heart = client.heart_rates(day.isoformat())
                upsert_daily(db, day, stats, heart)
                # Estos datos son opcionales en Garmin. Un fallo puntual no detiene el día.
                for method, sink in ((client.sleep, upsert_sleep), (client.hrv, upsert_hrv)):
                    try:
                        data = method(day.isoformat())
                        if data:
                            sink(db, day, data)
                    except GarminConnectTooManyRequestsError:
                        raise
                    except Exception as exc:
                        logger.info(
                            "Dato opcional no disponible para %s: %s", day, type(exc).__name__
                        )
                try:
                    upsert_training(
                        db,
                        day,
                        client.training_status(day.isoformat()),
                        client.training_readiness(day.isoformat()),
                    )
                except GarminConnectTooManyRequestsError:
                    raise
                except Exception:
                    pass
                state = self._state(db)
                state.progress_current, state.last_date_downloaded = (day - start).days + 1, day
                db.commit()
            time.sleep(self.settings.garmin_request_delay_seconds)
            day += timedelta(days=1)

    def _sync_weights(self, client: GarminClient, start: date, end: date) -> None:
        try:
            payload = client.weigh_ins(start.isoformat(), end.isoformat())
            with SessionLocal() as db:
                upsert_weights(db, payload)
                db.commit()
        except GarminConnectTooManyRequestsError:
            raise
        except Exception as exc:
            logger.info("Pesos no disponibles: %s", type(exc).__name__)


sync_service = SyncService()
