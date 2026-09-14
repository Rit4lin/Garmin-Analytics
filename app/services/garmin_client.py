import logging
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.config import Settings

logger = logging.getLogger(__name__)
TOKEN_ERROR = (
    "Los tokens de Garmin no son válidos. Ejecuta garmin-mcp-auth en el contenedor garmin-mcp."
)


class GarminTokenError(RuntimeError):
    pass


T = TypeVar("T")


class GarminClient:
    """Cliente de solo lectura: no conoce ni acepta usuario o contraseña."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Garmin | None = None
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0

    def _call(self, operation: Callable[[], T]) -> T:
        """Único punto de salida HTTP Garmin, con intervalo entre cada petición."""
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            delay = self.settings.garmin_request_delay_seconds - elapsed
            if delay > 0:
                time.sleep(delay + random.uniform(0, 0.15))
            try:
                return operation()
            finally:
                self._last_request_at = time.monotonic()

    def connect(self) -> Garmin:
        token_dir = Path(self.settings.garmin_tokens)
        if not (token_dir / "garmin_tokens.json").is_file():
            raise GarminTokenError(TOKEN_ERROR)
        try:
            # verify_login=False impide que la librería intente su cadena de login.
            # Con email/password a None sólo se reutiliza el token montado.
            client = Garmin(retry_attempts=0, verify_login=False)
            self._call(lambda: client.login(str(token_dir)))
            self.client = client
            return client
        except GarminConnectAuthenticationError as exc:
            logger.warning("Autenticación Garmin mediante token falló: %s", type(exc).__name__)
            raise GarminTokenError(TOKEN_ERROR) from exc
        except (GarminConnectTooManyRequestsError, GarminConnectConnectionError):
            raise

    def api(self) -> Garmin:
        return self.client or self.connect()

    def _api_call(self, operation: Callable[[Garmin], T]) -> T:
        client = self.api()
        return self._call(lambda: operation(client))

    def activities(self, start: str, end: str) -> list[dict[str, Any]]:
        return self._api_call(lambda client: client.get_activities_by_date(start, end))

    def activity_details(self, activity_id: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_activity_details(activity_id))

    def activity_splits(self, activity_id: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_activity_splits(activity_id))

    def stats(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_stats(day))

    def heart_rates(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_heart_rates(day))

    def sleep(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_sleep_data(day))

    def hrv(self, day: str) -> dict[str, Any] | None:
        return self._api_call(lambda client: client.get_hrv_data(day))

    def stress(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_stress_data(day))

    def spo2(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_spo2_data(day))

    def respiration(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_respiration_data(day))

    def body_battery(self, start: str, end: str) -> list[dict[str, Any]]:
        return self._api_call(lambda client: client.get_body_battery(start, end))

    def training_status(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_training_status(day))

    def training_readiness(self, day: str) -> list[dict[str, Any]]:
        return self._api_call(lambda client: client.get_training_readiness(day))

    def endurance_score(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_endurance_score(day))

    def hill_score(self, day: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_hill_score(day))

    def weigh_ins(self, start: str, end: str) -> dict[str, Any]:
        return self._api_call(lambda client: client.get_weigh_ins(start, end))

    def race_predictions(self, start: str | None = None, end: str | None = None) -> Any:
        if start and end:
            return self._api_call(
                lambda client: client.get_race_predictions(start, end, "daily")
            )
        return self._api_call(lambda client: client.get_race_predictions())

    def lactate_threshold(self) -> Any:
        return self._api_call(lambda client: client.get_lactate_threshold())

    def lactate_threshold_history(self, start: str, end: str) -> Any:
        return self._api_call(
            lambda client: client.get_lactate_threshold(
                latest=False,
                start_date=start,
                end_date=end,
                aggregation="daily",
            )
        )

    def running_tolerance(self, start: str, end: str) -> Any:
        return self._api_call(
            lambda client: client.get_running_tolerance(start, end, "daily")
        )

    def fitness_age(self, day: str) -> Any:
        return self._api_call(lambda client: client.get_fitnessage_data(day))

    def personal_records(self) -> Any:
        return self._api_call(lambda client: client.get_personal_record())
