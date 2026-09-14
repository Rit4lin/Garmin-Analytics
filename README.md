# Garmin Analytics 2.0

Aplicación personal, en español, para conservar y analizar los datos de Garmin Connect en una base SQLite propia. Está pensada para ejecutarse permanentemente en Unraid dentro de un único contenedor, en LAN o mediante VPN. No es un servicio médico ni debe exponerse directamente a Internet.

## Qué cambia en v2.0.0

La versión 2 convierte el panel de histórico en un analizador de evolución personal. En lugar de limitarse a mostrar valores actuales, compara el periodo reciente con una línea base móvil propia y trata de responder a una pregunta práctica: **¿mi rendimiento está mejorando, estable o empeorando?**

Incluye:

- Estado global de rendimiento con tendencia y confianza.
- Línea base personal móvil: 14 días recientes frente a los 42 días anteriores.
- Tendencias con porcentaje para VO₂max, Endurance, peso, Running Tolerance y otras señales.
- Eficiencia aeróbica basada en velocidad relativa a frecuencia cardiaca.
- Deriva cardiaca / aerobic decoupling a partir de los splits disponibles.
- Balance de carga aguda y crónica mediante EWMA de 7 y 42 días.
- Separación entre forma, carga y fatiga reciente.
- Recovery Score propio 0-100 usando HRV, FC en reposo, sueño, estrés, Body Battery y Training Readiness.
- Alertas automáticas de cambios relevantes respecto a la línea base.
- Comparación inteligente de una actividad con sesiones del mismo tipo y distancia parecida.
- Resumen independiente por disciplina para no mezclar carrera, fuerza y cardio.
- Histórico de Race Predictor para 5K, 10K, media maratón y maratón cuando Garmin lo facilita.
- Histórico y valor actual de umbral de lactato cuando está disponible.
- Running Tolerance y Fitness Age cuando Garmin los ofrece para la cuenta/dispositivo.
- Récords personales de Garmin, con estimaciones locales de carrera como alternativa.
- Panel de Insights que resume en lenguaje directo qué está cambiando y qué conviene vigilar.
- Acceso en la interfaz a métricas ya guardadas pero antes poco visibles: carga aguda, Recovery Time, Endurance Score, Hill Score, Body Battery mínimo, sueño despierto, potencia, cadencia y Training Effect.

Las métricas propias son analíticas y orientativas. No sustituyen las métricas de Garmin ni una valoración sanitaria.

## Arquitectura

```text
Garmin Connect
      ↓
python-garminconnect
      ↓
sincronizador conservador + limitador central
      ↓
SQLite (/data)
      ↓
normalización + motor de rendimiento v2
      ↓
FastAPI → dashboard Plotly + API
```

Usa Python 3.13, uv, FastAPI, SQLAlchemy 2.x, Alembic, APScheduler, Jinja2, Plotly y `garminconnect`.

La información principal se normaliza en tablas para actividades, estadísticas diarias, sueño, HRV, entrenamiento, peso, métricas de rendimiento y récords personales. La respuesta original de Garmin se conserva como JSON complementario cuando corresponde.

## Cómo interpreta la evolución

El motor usa una línea base personal en vez de comparar tus números contra valores de otras personas. Por defecto calcula la media de los últimos 14 días y la enfrenta a los 42 días previos. Las métricas donde menos es mejor, como FC en reposo, estrés, ritmo o tiempo previsto de carrera, invierten correctamente la dirección del cambio.

La eficiencia aeróbica se calcula como velocidad relativa a FC media. Esto permite detectar mejoras donde corres más rápido con un coste cardiaco similar o menor.

Para actividades con splits suficientes también se calcula la pérdida de eficiencia entre la primera y la segunda mitad de la sesión. Una deriva menor suele ser una señal útil de resistencia aeróbica en sesiones comparables.

La carga utiliza medias exponenciales de 7 y 42 días. El cociente entre ambas se emplea como una señal de carga reciente, no como una predicción clínica de lesión.

El Recovery Score propio combina desviaciones respecto a tu línea base de HRV, FC en reposo, sueño, estrés, Body Battery y Training Readiness. El dashboard explica los componentes para evitar convertir el resultado en un número opaco.

## Sincronización y datos

En una base vacía, el backfill de `INITIAL_SYNC_DAYS` se inicia en segundo plano; el dashboard continúa disponible. Después se revisan los días recientes cada `SYNC_INTERVAL_MINUTES`. Las escrituras son UPSERT: repetir una sincronización no duplica datos.

Se consultan exclusivamente métodos de `python-garminconnect`. El núcleo sincroniza:

- actividades, detalles y splits;
- estadísticas, pulso, estrés, SpO₂, respiración y Body Battery;
- sueño y HRV;
- Training Status, Training Readiness, VO₂max, carga, Endurance Score y Hill Score;
- peso y composición corporal;
- Race Predictor, umbral de lactato, Running Tolerance, Fitness Age y récords personales cuando estén disponibles.

Los endpoints de rendimiento adicionales son opcionales. Si Garmin no entrega una de esas métricas para la cuenta o dispositivo, no se bloquea el resto de la sincronización.

Los históricos que admiten rangos se solicitan en bloques de hasta 365 días para reducir tráfico. Todas las llamadas pasan por el limitador central `GARMIN_REQUEST_DELAY_SECONDS`, 0,8 segundos por defecto. Un HTTP 429 aplica backoff exponencial y bloquea también el botón manual hasta `next_retry_at`.

Nunca utiliza `GARMIN_EMAIL` ni `GARMIN_PASSWORD`.

## API v2

Además de los endpoints anteriores:

- `GET /api/performance?days=180`: estado global, tendencias, recovery, carga, disciplinas, alertas, insights, predicciones y récords.
- `GET /api/performance/timeseries?days=365`: series de Race Predictor, umbral y Running Tolerance.
- `GET /api/performance/raw?days=365`: métricas de rendimiento normalizadas.
- `GET /api/activities/{id}`: incluye eficiencia, aerobic decoupling y comparación con sesiones similares.

La documentación OpenAPI está disponible en `/docs`.

## Instalación local

Se requiere Python 3.13 y `uv`.

```bash
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Abre `http://localhost:8080`. El chequeo del contenedor está en `/healthz`.

## Docker

```bash
docker build -t garmin-analytics:local .
docker run --rm -p 8080:8080 \
  -v /ruta/data:/data \
  -v /ruta/tokens:/root/.garminconnect \
  garmin-analytics:local
```

La imagen es `linux/amd64`, usa un único proceso Uvicorn y arranca aunque Garmin esté temporalmente inaccesible para permitir consultar el histórico local.

## Instalación en Unraid

En la GUI nativa de Unraid crea el contenedor con estos campos:

| Campo | Valor |
|---|---|
| Repository | `ghcr.io/rit4lin/garmin-analytics:latest` |
| Port Host / Container / Type | `8010` / `8080` / `TCP` |
| Garmin Analytics Data | `/mnt/user/appdata/garmin-analytics/data` → `/data` Read/Write |
| Garmin Tokens | `/mnt/user/appdata/garmin-mcp/tokens` → `/root/.garminconnect` Read/Write |

Variables recomendadas:

| Variable | Valor |
|---|---|
| `GARMINTOKENS` | `/root/.garminconnect` |
| `DATABASE_URL` | `sqlite:////data/garmin-analytics.db` |
| `INITIAL_SYNC_DAYS` | `365` |
| `SYNC_INTERVAL_MINUTES` | `180` |
| `GARMIN_REQUEST_DELAY_SECONDS` | `0.8` |
| `TZ` | `Europe/Madrid` |

No añadas `GARMIN_EMAIL` ni `GARMIN_PASSWORD`. El volumen de tokens se comparte, sin copiar, con `garmin-mcp`. Si los tokens caducan o son revocados, renueva la autenticación con `garmin-mcp-auth` en ese contenedor.

## Migración a 2.0

Alembic crea automáticamente las tablas `performance_metrics` y `personal_records` al arrancar. La migración no borra el histórico existente de actividades, salud, sueño, HRV, entrenamiento o peso.

Tras actualizar, la primera sincronización completa los datos v2 que Garmin pueda proporcionar dentro del intervalo de sincronización. Los análisis que dependen sólo de datos ya guardados, como eficiencia, carga y recuperación, funcionan sin esperar a esos endpoints opcionales.

## Tests, CI y publicación

```bash
uv sync --group dev
uv run ruff check .
uv run pytest
```

GitHub Actions ejecuta las comprobaciones en cada PR contra `main`. Los pushes a `main` publican `latest`, `main`, `build-N` y `sha-xxxxxxx` en GHCR. Los tags SemVer publican también las etiquetas correspondientes.

La referencia de esta gran actualización es **`v2.0.0`**.

## Backups, seguridad y rollback

Incluye `/mnt/user/appdata/garmin-analytics/data` en las copias de seguridad de Unraid. Los tokens de `/mnt/user/appdata/garmin-mcp/tokens` son secretos equivalentes a una contraseña: no los dupliques, publiques ni subas a Git.

Si una actualización falla, puedes cambiar temporalmente el repositorio de Unraid a una imagen `build-N` o `sha-xxxxxxx` anterior y reiniciar el contenedor.

Mantén este servicio dentro de tu LAN o detrás de una VPN. No abras el puerto 8010 directamente a Internet.
