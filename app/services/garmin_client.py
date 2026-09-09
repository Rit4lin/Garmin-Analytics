import logging
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from app.config import Settings

logger = logging.getLogger(__name__)
TOKEN_ERROR = (
    "Los tokens de Garmin no son válidos. Ejecuta garmin-mcp-auth en el contenedor garmin-mcp."
)


class GarminTokenError(RuntimeError):
    pass


class GarminClient:
    """Cliente de solo lectura: no conoce ni acepta usuario o contraseña."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Garmin | None = None

    def connect(self) -> Garmin:
        token_dir = Path(self.settings.garmin_tokens)
        if not (token_dir / "garmin_tokens.json").is_file():
            raise GarminTokenError(TOKEN_ERROR)
        try:
            # verify_login=False impide que la librería intente su cadena de login.
            # Con email/password a None sólo se reutiliza el token montado.
            client = Garmin(retry_attempts=0, verify_login=False)
            client.login(str(token_dir))
            self.client = client
            return client
        except Exception as exc:
            logger.warning("Autenticación Garmin mediante token falló: %s", type(exc).__name__)
            raise GarminTokenError(TOKEN_ERROR) from exc

    def api(self) -> Garmin:
        return self.client or self.connect()

    def activities(self, start: str, end: str) -> list[dict[str, Any]]:
        return self.api().get_activities_by_date(start, end)

    def activity_details(self, activity_id: str) -> dict[str, Any]:
        return self.api().get_activity_details(activity_id)

    def activity_splits(self, activity_id: str) -> dict[str, Any]:
        return self.api().get_activity_splits(activity_id)

    def stats(self, day: str) -> dict[str, Any]:
        return self.api().get_stats(day)

    def heart_rates(self, day: str) -> dict[str, Any]:
        return self.api().get_heart_rates(day)

    def sleep(self, day: str) -> dict[str, Any]:
        return self.api().get_sleep_data(day)

    def hrv(self, day: str) -> dict[str, Any] | None:
        return self.api().get_hrv_data(day)

    def stress(self, day: str) -> dict[str, Any]:
        return self.api().get_stress_data(day)

    def spo2(self, day: str) -> dict[str, Any]:
        return self.api().get_spo2_data(day)

    def respiration(self, day: str) -> dict[str, Any]:
        return self.api().get_respiration_data(day)

    def training_status(self, day: str) -> dict[str, Any]:
        return self.api().get_training_status(day)

    def training_readiness(self, day: str) -> list[dict[str, Any]]:
        return self.api().get_training_readiness(day)

    def weigh_ins(self, start: str, end: str) -> dict[str, Any]:
        return self.api().get_weigh_ins(start, end)
