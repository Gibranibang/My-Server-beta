"""
E2E Test Helpers & Mock Infrastructure for MyServer Desktop Alpha.
Provides isolated HTTP mock server, notification interceptors, and temporary config environments.
"""

import os
import sys
import json
import time
import socket
import tempfile
import shutil
import threading
import http.server
from urllib.parse import urlparse

# Ensure project root is in sys.path
ALPHA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ALPHA_DIR not in sys.path:
    sys.path.insert(0, ALPHA_DIR)

import config_manager


class MockZimaHandler(http.server.BaseHTTPRequestHandler):
    """Configurable HTTP request handler simulating ZimaOS API endpoints."""

    def log_message(self, format, *args):
        # Suppress standard HTTP server console logging during tests
        pass

    @property
    def server_instance(self):
        return self.server

    def _read_body_json(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 0:
            raw = self.rfile.read(content_len).decode("utf-8")
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}
        return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        self.server_instance.recorded_requests.append({
            "method": "GET",
            "path": self.path,
            "headers": dict(self.headers),
        })

        route_handler = self.server_instance.routes.get(("GET", path))
        if route_handler:
            status_code, body = route_handler(self)
        elif ("GET", path) in self.server_instance.default_responses:
            status_code, body = self.server_instance.default_responses[("GET", path)]
        else:
            status_code, body = 404, {"error": "Not Found", "path": path}

        self._send_json(status_code, body)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body_json = self._read_body_json()
        self.server_instance.recorded_requests.append({
            "method": "POST",
            "path": self.path,
            "headers": dict(self.headers),
            "body": body_json,
        })

        route_handler = self.server_instance.routes.get(("POST", path))
        if route_handler:
            status_code, body = route_handler(self, body_json)
        elif ("POST", path) in self.server_instance.default_responses:
            status_code, body = self.server_instance.default_responses[("POST", path)]
        else:
            status_code, body = 404, {"error": "Not Found", "path": path}

        self._send_json(status_code, body)

    def _send_json(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        resp_bytes = json.dumps(body).encode("utf-8")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)


class MockZimaServer:
    """Lightweight in-process HTTP mock server running on an ephemeral port."""

    def __init__(self):
        self.server = None
        self.thread = None
        self.port = 0
        self.recorded_requests = []
        self.routes = {}
        self.default_responses = {}
        self._setup_defaults()

    def _setup_defaults(self):
        # Default valid responses for ZimaOS endpoints
        self.default_responses[("GET", "/v1/sys/utilization")] = (200, {
            "data": {
                "cpu": {
                    "percent": 25.0,
                    "usage": 25.0,
                    "temperature": 45.0,
                    "power": {"energy": 1000, "time": 100},
                },
                "mem": {
                    "used": 4 * 1024 * 1024 * 1024,
                    "total": 16 * 1024 * 1024 * 1024,
                    "usedPercent": 25.0,
                },
                "sys_disk": {
                    "size": 500 * 1024 * 1024 * 1024,
                    "used": 100 * 1024 * 1024 * 1024,
                },
            }
        })

        self.default_responses[("GET", "/v1/sys/hardware")] = (200, {
            "data": {
                "cpu": {
                    "temperature": 45.0,
                    "modelName": "Intel(R) Core(TM) i5-1135G7",
                }
            }
        })

        self.default_responses[("GET", "/v1/users/current")] = (200, {
            "data": {
                "id": 1,
                "role": "admin",
                "is_admin": True,
                "username": "admin",
            }
        })

        self.default_responses[("GET", "/v2/local_storage/mount")] = (200, {
            "data": [
                {
                    "mount_point": "/DATA",
                    "fstype": "ext4",
                    "total": 500 * 1024 * 1024 * 1024,
                    "used": 100 * 1024 * 1024 * 1024,
                }
            ]
        })

        # Default auth response accepts user "admin" / "password123"
        def default_login_handler(handler, body):
            username = body.get("username") or body.get("name")
            password = body.get("password")
            if username == "admin" and password == "password123":
                # Header: {"alg":"HS256","typ":"JWT"}
                # Payload: {"id":1,"role":"admin","is_admin":true,"sub":"admin"}
                dummy_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MSwicm9sZSI6ImFkbWluIiwiaXNfYWRtaW4iOnRydWUsInN1YiI6ImFkbWluIn0.signature"
                return 200, {
                    "data": {
                        "token": dummy_token,
                        "access_token": dummy_token,
                    }
                }
            return 401, {"message": "username or password invalid", "code": 401}

        self.routes[("POST", "/v1/users/login")] = default_login_handler

    def set_route(self, method, path, handler_or_tuple):
        """Set a custom response or callback for method + path."""
        key = (method.upper(), path)
        if callable(handler_or_tuple):
            self.routes[key] = handler_or_tuple
        else:
            self.routes.pop(key, None)
            self.default_responses[key] = handler_or_tuple

    def start(self):
        class ThreadedHTTPServer(http.server.HTTPServer):
            pass

        self.server = ThreadedHTTPServer(("127.0.0.1", 0), MockZimaHandler)
        self.server.recorded_requests = self.recorded_requests
        self.server.routes = self.routes
        self.server.default_responses = self.default_responses
        self.port = self.server.server_address[1]

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # Give server thread a moment to bind and listen
        time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


class NotificationSpy:
    """Intercepter spy for send_notification and prompt_alert to prevent UI popups and track calls."""

    def __init__(self):
        self.notifications = []
        self.alerts = []
        self.confirms = []
        self._orig_send_notification = None
        self._orig_prompt_alert = None
        self._orig_prompt_confirm = None

    def __enter__(self):
        import zimaos_app
        import dialog_helper

        self._orig_send_notification = getattr(zimaos_app, "send_notification", None)
        self._orig_prompt_alert = getattr(dialog_helper, "prompt_alert", None)
        self._orig_prompt_confirm = getattr(dialog_helper, "prompt_confirm", None)

        def spy_notification(title, message):
            self.notifications.append({"title": title, "message": message, "time": time.time()})

        def spy_alert(title, text):
            self.alerts.append({"title": title, "text": text, "time": time.time()})

        def spy_confirm(title, prompt_text):
            self.confirms.append({"title": title, "text": prompt_text, "time": time.time()})
            return True

        if hasattr(zimaos_app, "send_notification"):
            zimaos_app.send_notification = spy_notification
        if hasattr(dialog_helper, "prompt_alert"):
            dialog_helper.prompt_alert = spy_alert
        if hasattr(dialog_helper, "prompt_confirm"):
            dialog_helper.prompt_confirm = spy_confirm

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import zimaos_app
        import dialog_helper

        if self._orig_send_notification is not None:
            zimaos_app.send_notification = self._orig_send_notification
        if self._orig_prompt_alert is not None:
            dialog_helper.prompt_alert = self._orig_prompt_alert
        if self._orig_prompt_confirm is not None:
            dialog_helper.prompt_confirm = self._orig_prompt_confirm


class IsolatedConfigEnv:
    """Creates a temporary workspace with isolated config.json for safe tests."""

    def __init__(self, initial_config=None):
        self.temp_dir = None
        self.initial_config = initial_config
        self._orig_get_base_dir = None

    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="myserver_test_env_")
        self._orig_get_base_dir = config_manager.get_base_dir

        temp_dir = self.temp_dir
        config_manager.get_base_dir = lambda: temp_dir

        if self.initial_config is not None:
            config_path = os.path.join(self.temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.initial_config, f, indent=4)

        return self.temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        config_manager.get_base_dir = self._orig_get_base_dir
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass
