#!/usr/bin/env python3
"""Run only on the authorized host; immutable release -> private test workspace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path("/home/ubuntu/ChiHuiTong")
PG_BIN = Path("/usr/lib/postgresql/16/bin")
SERVICES = ["chihui-public.service", "study-system-web.service", "study-system-syncthing.service", "nginx.service"]


def checked(command, **kwargs):
    return subprocess.run(command, check=True, text=True, timeout=60, **kwargs)


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def service_states():
    return {name: subprocess.run(["systemctl", "is-active", name], text=True, capture_output=True).stdout.strip() for name in SERVICES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-migrations", action="store_true")
    parser.add_argument("--format", action="store_true", help="Format only disposable workspace, then retrieve reviewed generated files")
    parser.add_argument("--labels", nargs="*", default=["chihuitong.tests"])
    args = parser.parse_args()
    if sys.platform != "linux" or socket.gethostname() != "VM-0-12-ubuntu" or os.getuid() == 0:
        raise SystemExit("只能在指定开发服务器以ubuntu身份运行")
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT / "releases" or len(release.name) != 40 or not all(c in "0123456789abcdef" for c in release.name):
        raise SystemExit("必须从已校验提交快照运行")
    if (release / ".git").exists():
        raise SystemExit("服务器不能有本项目Git仓库")
    os.umask(0o077)
    import fcntl
    (ROOT / "runtime").mkdir(exist_ok=True)
    lock = (ROOT / "runtime" / "backend-tests.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("已有后端测试运行，禁止并发重建同一个测试库") from None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_dir = ROOT / "test-results" / f"{stamp}-{release.name[:12]}-backend"
    result_dir.mkdir(parents=True)
    workspace = result_dir / "workspace"
    shutil.copytree(release / "backend", workspace)
    baseline = hashes(release)
    before = service_states()
    summary = {"host": socket.gethostname(), "commit": release.name, "started_at": stamp, "services_before": before, "steps": [], "passed": False}
    print(f"BACKEND_REPORT={result_dir / 'summary.json'}", flush=True)
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    pg_data = runtime / "postgres"
    pg_socket = runtime / "pgsocket"
    pg_socket.mkdir(exist_ok=True, mode=0o700)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    python = ROOT / ".venv-backend" / "bin" / "python"

    def step(name, command, *, cwd=workspace, acceptable=(0,)):
        logfile = result_dir / f"{name}.log"
        with logfile.open("w") as output:
            try:
                completed = subprocess.run([str(c) for c in command], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, text=True, timeout=900)
            except subprocess.TimeoutExpired:
                summary["steps"].append({"name": name, "exit_code": "timeout", "log": str(logfile)})
                raise RuntimeError(f"{name} exceeded 15 minute safety deadline") from None
        summary["steps"].append({"name": name, "exit_code": completed.returncode, "log": str(logfile)})
        print(f"{name}: exit={completed.returncode}", flush=True)
        if completed.returncode not in acceptable:
            # Test output uses synthetic data; never dump environment or generated secret files.
            print(logfile.read_text()[-12000:], flush=True)
            raise RuntimeError(f"{name} failed")

    try:
        if not python.exists():
            step("create-venv", [sys.executable, "-m", "venv", ROOT / ".venv-backend"])
        step("dependencies", [python, "-m", "pip", "install", "--disable-pip-version-check", "-r", workspace / "requirements-dev.txt"])
        step("pip-check", [python, "-m", "pip", "check"])
        if not (pg_data / "PG_VERSION").exists():
            if pg_data.exists():
                raise RuntimeError("PG目录已存在但不是完整实例，请人工检查；不覆盖")
            step("initdb", [PG_BIN / "initdb", "-D", pg_data, "--auth-local=peer", "--auth-host=reject", "--encoding=UTF8", "--no-locale"])
        if (pg_data / "PG_VERSION").read_text().strip() != "16":
            raise RuntimeError("测试数据库版本不匹配")
        if subprocess.run([str(PG_BIN / "pg_ctl"), "-D", str(pg_data), "status"], stdout=subprocess.DEVNULL).returncode != 0:
            options = f"-c listen_addresses='' -c unix_socket_directories={pg_socket} -p 55432 -c shared_buffers=64MB -c max_connections=30"
            step("start-postgres", [PG_BIN / "pg_ctl", "-D", pg_data, "-l", runtime / "postgres.log", "-o", options, "-w", "start"])
        identity = checked([PG_BIN / "psql", "-h", pg_socket, "-p", "55432", "-d", "postgres", "-Atc", "SHOW data_directory"], capture_output=True).stdout.strip()
        if Path(identity).resolve() != pg_data.resolve():
            raise RuntimeError("拒绝连接非本项目数据库")
        exists = checked([PG_BIN / "psql", "-h", pg_socket, "-p", "55432", "-d", "postgres", "-Atc", "SELECT 1 FROM pg_database WHERE datname='chihuitong_dev'"], capture_output=True).stdout.strip()
        if not exists:
            step("create-database", [PG_BIN / "createdb", "-h", pg_socket, "-p", "55432", "chihuitong_dev"])
        secret_path = runtime / "backend-test-secrets.json"
        if not secret_path.exists():
            import base64
            secret_path.write_text(json.dumps({"CHT_SECRET_KEY": secrets.token_urlsafe(48), "CHT_FIELD_KEYS": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), "CHT_PHONE_INDEX_KEY": secrets.token_urlsafe(48)}))
            secret_path.chmod(0o600)
        env.update(json.loads(secret_path.read_text()))
        env.update({"CHT_ENVIRONMENT": "test", "CHT_ALLOWED_HOSTS": "localhost,127.0.0.1,testserver", "CHT_DB_HOST": str(pg_socket), "CHT_DB_PORT": "55432", "CHT_DB_NAME": "chihuitong_dev", "CHT_DB_USER": "ubuntu", "CHT_TEST_DB_NAME": "test_chihuitong", "CHT_PRIVATE_STORAGE": str(result_dir / "private-files")})
        if args.format:
            step("lint-fix", [python, "-m", "ruff", "check", "--fix", "."], acceptable=(0, 1))
            step("format", [python, "-m", "ruff", "format", "."])
        step("lint", [python, "-m", "ruff", "check", "."])
        step("format-check", [python, "-m", "ruff", "format", "--check", "."])
        if args.generate_migrations:
            step("generate-migrations", [python, "manage.py", "makemigrations", "chihuitong"])
        step("migration-check", [python, "manage.py", "makemigrations", "--check", "--dry-run"])
        step("migrate", [python, "manage.py", "migrate", "--noinput"])
        step("django-check", [python, "manage.py", "check"])
        step("http-smoke", [python, workspace / "smoke_http.py"])
        step("tests", [python, "-m", "coverage", "run", "manage.py", "test", *args.labels, "--noinput", "--verbosity", "2"])
        step("coverage", [python, "-m", "coverage", "report"])
        step("coverage-json", [python, "-m", "coverage", "json", "-o", result_dir / "coverage.json"])
        summary["passed"] = True
    finally:
        summary["services_after"] = service_states()
        summary["release_unchanged"] = baseline == hashes(release)
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        if summary["services_after"] != before or not summary["release_unchanged"]:
            summary["passed"] = False
        (result_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"BACKEND_PASSED={summary['passed']}", flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
