# Garmin Analytics

Aplicación personal, en español, para conservar y analizar los datos de Garmin Connect en una base SQLite propia. Está pensada para ejecutarse permanentemente en Unraid dentro de un único contenedor. No es un servicio médico ni debe exponerse a Internet.

## Arquitectura

```text
Garmin Connect → python-garminconnect → sincronizador conservador → SQLite (/data) → FastAPI → dashboard Plotly
```

Usa Python 3.13, uv, FastAPI, SQLAlchemy 2.x, Alembic, APScheduler, Jinja2, Plotly y `garminconnect`. La información principal se normaliza (actividades, estadísticas diarias, sueño, HRV, entrenamiento y peso) y la respuesta original de Garmin se conserva como JSON complementario.

## Sincronización y datos

En una base vacía, el backfill de `INITIAL_SYNC_DAYS` se inicia en segundo plano; el dashboard continúa disponible. Después sólo se revisan los últimos siete días y las actividades del intervalo, cada `SYNC_INTERVAL_MINUTES`. Las escrituras son UPSERT: repetir una sincronización no duplica datos. El estado, progreso, última fecha y errores están visibles en la interfaz y en `/api/sync/status`.

Se consultan exclusivamente métodos existentes de `python-garminconnect`: actividades, detalles y splits; estadísticas, pulso, estrés, SpO2, respiración, Body Battery, sueño, HRV, estado/readiness de entrenamiento, endurance/hill score y pesos. Algunas métricas dependen de la cuenta/dispositivo y se muestran sólo si están disponibles. Los detalles/splits de una actividad nueva se guardan una vez para limitar peticiones.

El backfill se ejecuta una sola vez y guarda un cursor persistente tras cada día completo. Si se interrumpe, continúa desde el día siguiente al cursor; después de completarse, los reinicios sólo revisan los últimos siete días. Todas las llamadas Garmin pasan por un limitador central de `GARMIN_REQUEST_DELAY_SECONDS` (0,8 segundos por defecto). Un HTTP 429 aplica backoff exponencial y bloquea también el botón manual hasta `next_retry_at`; el estado devuelve los segundos restantes. Los datos opcionales que Garmin no entregue no bloquean el resto. Nunca utiliza `GARMIN_EMAIL` ni `GARMIN_PASSWORD`.

## Instalación local

Se requiere Python 3.13 y [uv](https://docs.astral.sh/uv/). Copia `.env.example` a `.env` y ajusta rutas locales seguras. No copies tokens al repositorio.

```bash
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Abre `http://localhost:8080`. La API documentada está en `/docs` y el chequeo de contenedor en `/healthz`.

## Docker

```bash
docker build -t garmin-analytics:local .
docker run --rm -p 8080:8080 -v /ruta/data:/data -v /ruta/tokens:/root/.garminconnect garmin-analytics:local
```

La imagen es exclusivamente `linux/amd64`, usa un único proceso Uvicorn y tiene `HEALTHCHECK` sobre `/healthz`. Arranca aunque Garmin esté inaccesible y permite consultar el histórico ya almacenado.

## Instalación en Unraid

En la GUI nativa de Unraid crea el contenedor con estos campos exactos:

| Campo | Valor |
|---|---|
| Repository | `ghcr.io/rit4lin/garmin-analytics:latest` |
| Port (Host / Container / Type) | `8010` / `8080` / `TCP` |
| Path 1 Name | Garmin Analytics Data |
| Path 1 Host / Container / Access | `/mnt/user/appdata/garmin-analytics/data` / `/data` / Read/Write |
| Path 2 Name | Garmin Tokens |
| Path 2 Host / Container / Access | `/mnt/user/appdata/garmin-mcp/tokens` / `/root/.garminconnect` / Read/Write |

Variables:

| Variable | Valor |
|---|---|
| `GARMINTOKENS` | `/root/.garminconnect` |
| `DATABASE_URL` | `sqlite:////data/garmin-analytics.db` |
| `INITIAL_SYNC_DAYS` | `365` |
| `SYNC_INTERVAL_MINUTES` | `180` |
| `GARMIN_REQUEST_DELAY_SECONDS` | `0.8` |
| `TZ` | `Europe/Madrid` |

No añadas `GARMIN_EMAIL` ni `GARMIN_PASSWORD`. El segundo volumen comparte, sin copiar, los tokens con `garmin-mcp`. No borres ni recrees el directorio de tokens: si están caducados o revocados, Garmin Analytics mostrará: “Los tokens de Garmin no son válidos. Ejecuta garmin-mcp-auth en el contenedor garmin-mcp.” Ejecuta ese comando allí y vuelve a sincronizar.

## GitHub, GHCR y rollback

El flujo de GitHub Actions usa el lockfile, ruff y tests en cada PR contra `main`; en `main` sólo publica si esas comprobaciones pasan. Publica `latest`, `main`, `build-N` y `sha-xxxxxxx`; un tag `v1.2.3` publica `1.2.3`, `1.2` y `1`.

Uso normal: `ghcr.io/rit4lin/garmin-analytics:latest`.

Si una actualización falla, cambia temporalmente el repositorio de Unraid a `ghcr.io/rit4lin/garmin-analytics:build-N` o `ghcr.io/rit4lin/garmin-analytics:sha-xxxxxxx` y reinicia el contenedor.

## Actualizar dependencias

Comprueba releases estables en PyPI/documentación oficial, edita los pines en `pyproject.toml`, y ejecuta:

```bash
uv lock --upgrade
uv sync --group dev
uv run ruff check .
uv run pytest
```

Revisa `uv.lock` antes de confirmar los cambios. No aceptes alphas, betas, dev ni RCs.

## Backups, seguridad y solución de problemas

Incluye `/mnt/user/appdata/garmin-analytics/data` en las copias de seguridad de Unraid: ahí vive toda la base histórica. Los tokens pertenecen a `/mnt/user/appdata/garmin-mcp/tokens` y son secretos equivalentes a una contraseña; no los dupliques, compartas, imprimas ni subas a Git.

Si aparece HTTP 429, deja que finalice el periodo de espera y reduce la frecuencia si persiste; no pulses repetidamente “Sincronizar ahora”. Si el panel muestra el mensaje de tokens inválidos, renueva la autenticación sólo con `garmin-mcp-auth` en el otro contenedor. Mantén este servicio en LAN, detrás de tu red local o VPN; no abras el puerto directamente a Internet.
