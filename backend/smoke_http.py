"""Ephemeral loopback-only WSGI smoke, invoked by the authorized remote test runner."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    if (
        sys.platform != "linux"
        or socket.gethostname() != "VM-0-12-ubuntu"
        or os.environ.get("CHT_ENVIRONMENT") != "test"
    ):
        raise SystemExit("只能在指定开发测试环境执行")
    directory = Path.cwd().resolve()
    if not directory.is_relative_to("/home/ubuntu/ChiHuiTong/test-results"):
        raise SystemExit("必须在独立测试副本执行")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path):
        try:
            with opener.open(f"http://127.0.0.1:{port}/api/v1/{path}", timeout=2) as response:
                return response.status, response.headers, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, response.headers, json.loads(response.read())

    with (directory.parent / "gunicorn-smoke.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gunicorn",
                "config.wsgi:application",
                "--bind",
                f"127.0.0.1:{port}",
                "--workers",
                "1",
                "--timeout",
                "15",
                "--graceful-timeout",
                "5",
                "--error-logfile",
                "-",
            ],
            cwd=directory,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError("WSGI进程提前退出，请查看独立冒烟日志")
                try:
                    status, headers, body = request("health")
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("WSGI启动超时") from None
                    time.sleep(0.2)
            assert status == 200 and body == {"status": "ok", "service": "chihuitong"}
            assert headers.get("X-Content-Type-Options") == "nosniff"
            for endpoint in ["organizations", "mini/customer/benefits", "mini/clinic/bills"]:
                status, _, body = request(endpoint)
                assert status == 401, (endpoint, status)
                assert "traceback" not in str(body).lower()
            print(
                "HTTP_SMOKE: WSGI, database health, Web/customer/clinic anonymous isolation passed"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
