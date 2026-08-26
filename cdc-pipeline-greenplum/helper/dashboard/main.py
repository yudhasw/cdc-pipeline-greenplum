from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backends import get_backend
from monitoring.health import get_health
from monitoring.logs import fetch_logs, list_containers
from monitoring import generator as gen

app = FastAPI()


@app.post("/api/generator/start")
def generator_start(interval: float = 5.0):
    return gen.start(interval_seconds=interval)


@app.post("/api/generator/stop")
def generator_stop():
    return gen.stop()


@app.get("/api/generator/status")
def generator_status():
    return gen.status()


@app.get("/api/health")
def health():
    return get_health()


@app.get("/api/logs")
def logs_list():
    return {"containers": list_containers()}


@app.get("/api/logs/{container}")
def logs_view(container: str, tail: int = 200):
    try:
        return {"container": container, "lines": fetch_logs(container, tail=tail)}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/analytics/employees")
def analytics_employees():
    return get_backend().employees_count()


@app.get("/api/analytics/latest")
def analytics_latest():
    return get_backend().latest_documents()


@app.get("/api/analytics/recent-deleted")
def analytics_recent_deleted():
    return get_backend().recent_deleted()


@app.get("/api/analytics/week-count")
def analytics_week_count():
    return get_backend().week_count()


@app.get("/api/analytics/week-status")
def analytics_week_status():
    return get_backend().week_status()


@app.get("/api/analytics/5-latest-account-created")
def analytics_5_latest_account_created():
    return get_backend().latest_accounts()


app.mount("/", StaticFiles(directory="static", html=True), name="static")
