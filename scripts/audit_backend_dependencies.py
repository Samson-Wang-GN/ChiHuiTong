"""Audit this project's installed environment only; never alter packages automatically."""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/ChiHuiTong")


def main():
    if sys.platform != "linux" or socket.gethostname() != "VM-0-12-ubuntu" or os.getuid() == 0:
        raise SystemExit("只能在指定服务器以ubuntu运行")
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT / "releases" or len(release.name) != 40:
        raise SystemExit("必须从提交快照运行")
    os.umask(0o077)
    report = ROOT / "test-results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-dependency-audit")
    report.mkdir()
    auditor = ROOT / ".venv-audit" / "bin" / "python"
    with (report / "audit.log").open("w") as log:
        if not auditor.exists():
            subprocess.run([sys.executable, "-m", "venv", auditor.parents[1]], check=True, timeout=60, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([auditor, "-m", "pip", "install", "--disable-pip-version-check", "pip-audit==2.10.1"], check=True, timeout=300, stdout=log, stderr=subprocess.STDOUT)
        process = subprocess.run([auditor, "-m", "pip_audit", "--path", ROOT / ".venv-backend/lib/python3.12/site-packages", "--strict", "--progress-spinner", "off", "--timeout", "15", "--format", "json", "--output", report / "audit.json"], timeout=600, stdout=log, stderr=subprocess.STDOUT)
    summary = {"commit": release.name, "exit_code": process.returncode, "report": str(report), "passed": False}
    if (report / "audit.json").exists():
        data = json.loads((report / "audit.json").read_text())
        summary["packages"] = len(data.get("dependencies", []))
        summary["findings"] = [{"name": item["name"], "version": item.get("version"), "skip_reason": item.get("skip_reason"),
                                "vulnerabilities": [{"id": vulnerability["id"], "fix_versions": vulnerability.get("fix_versions", [])} for vulnerability in item.get("vulns", [])]}
                               for item in data.get("dependencies", []) if item.get("vulns") or item.get("skip_reason")]
        summary["passed"] = process.returncode == 0 and not summary["findings"]
    (report / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
