from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import scripts.status_api as status_api
from visitor_counter.configuration import AppConfig, save_config


def test_status_api_requires_bearer_auth_but_exposes_minimal_health(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    save_config(AppConfig(), tmp_path / "config" / "config.yaml")
    status_api.StatusHandler.project_root = tmp_path
    status_api.StatusHandler.app_config = AppConfig()
    status_api.StatusHandler.tokens = {
        "viewer": "v" * 32,
        "operator": "o" * 32,
        "admin": "a" * 32,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), status_api.StatusHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/health", timeout=3) as response:
            payload = json.loads(response.read())
            assert payload == {"service": "visitor-counter", "status": "available"}
            assert response.headers["Cache-Control"].startswith("no-store")
        try:
            urlopen(f"{base}/api/v1/counts/current", timeout=3)
        except HTTPError as exc:
            assert exc.code == 401
            assert exc.headers["WWW-Authenticate"].startswith("Bearer")
        else:
            raise AssertionError("protected endpoint accepted an unauthenticated request")

        request = Request(f"{base}/api/v1/privacy/export", method="POST", data=b"{}")
        request.add_header("Authorization", f"Bearer {'v' * 32}")
        request.add_header("Content-Type", "application/json")
        try:
            urlopen(request, timeout=3)
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("viewer role was allowed to export personal data")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
