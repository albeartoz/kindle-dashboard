from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_file

from app.config import load_config
from app.render import render_dashboard
from app.service import DashboardService

config = load_config()
service = DashboardService(config)

app = Flask(__name__)


@app.before_request
def _ensure_started() -> None:
    if request.endpoint == "health":
        return
    service.start()


@app.get("/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@app.get("/debug.json")
def debug_json():
    return jsonify(service.payload.as_dict())


@app.post("/refresh")
def refresh():
    payload = service.refresh_all()
    return jsonify(payload.as_dict())


@app.get("/")
def index():
    return (
        "<html><head><meta http-equiv='refresh' content='60'></head>"
        "<body style='margin:0;background:#fff'>"
        "<img src='/dashboard.png' style='width:100vw;height:100vh;object-fit:contain'>"
        "</body></html>"
    )


@app.get("/dashboard.png")
def dashboard_png():
    output = Path(config.dashboard.output_path).resolve()
    if not output.exists():
        output = render_dashboard(service.payload, config).resolve()
    return send_file(output, mimetype="image/png", max_age=0)


if __name__ == "__main__":
    service.start()
    app.run(host=config.server.host, port=config.server.port, use_reloader=False)
