import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import init_database
from app.routers.api import router as api_router
from app.services.sync_service import sync_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    scheduler = BackgroundScheduler(timezone=get_settings().tz)
    scheduler.add_job(
        sync_service.request_sync,
        "interval",
        minutes=get_settings().sync_interval_minutes,
        id="garmin-sync",
        replace_existing=True,
    )
    scheduler.start()
    sync_service.request_sync()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Garmin Analytics", version="2.0.0", lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
