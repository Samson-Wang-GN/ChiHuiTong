"""Run existing prototype checks only on the approved development server."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SERVER_ROOT = Path('/home/ubuntu/ChiHuiTong')
SERVER_HOSTNAME = 'VM-0-12-ubuntu'
SUITES = [
    'verify_excel_import.py',
    'verify.py', 'verify_contracts.py', 'verify_tabs.py',
    'verify_workflows.py', 'verify_contract_groups.py', 'verify_mini.py',
    'verify_operations.py', 'verify_settlement.py', 'verify_sales.py',
    'verify_overview.py', 'verify_overdue.py', 'verify_institutions.py',
    'verify_clinic_info.py', 'verify_clinic_review.py', 'verify_management.py',
    'verify_mobile_access.py', 'verify_rules29.py', 'verify_floating.py',
]


def source_hashes(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*')) if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['all', 'smoke', 'import'], default='all')
    args = parser.parse_args()
    release = Path(__file__).resolve().parents[1]
    if sys.platform != 'linux' or socket.gethostname() != SERVER_HOSTNAME:
        raise SystemExit('REFUSED: tests may run only on the approved development server')
    if release.parent != SERVER_ROOT / 'releases' or not release.name.isalnum():
        raise SystemExit('REFUSED: run from a synced release under /home/ubuntu/ChiHuiTong/releases')
    if (release / '.git').exists():
        raise SystemExit('REFUSED: the server must not host the project Git mirror')
    # Do not borrow or terminate an unrelated service on the shared server.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8765))
    started = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + release.name[:12]
    result_dir = SERVER_ROOT / 'test-results' / run_id
    result_dir.mkdir(parents=True, exist_ok=False)
    before = source_hashes(release)
    workspace = result_dir / 'workspace'
    shutil.copytree(release, workspace)
    suites = SUITES if args.suite == 'all' else ['verify_excel_import.py', 'verify_sales.py'] if args.suite == 'import' else ['verify.py', 'verify_rules29.py', 'verify_floating.py']
    results = []
    server = None
    try:
        with (result_dir / 'http.log').open('w', encoding='utf-8') as http_log:
            server = subprocess.Popen(
                [sys.executable, '-m', 'http.server', '8765', '--bind', '127.0.0.1',
                 '--directory', str(workspace / 'prototypes')],
                stdout=http_log, stderr=subprocess.STDOUT,
            )
            for _ in range(50):
                if server.poll() is not None:
                    raise RuntimeError('isolated HTTP server exited; see http.log')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765/clinic/', timeout=1) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise RuntimeError('isolated HTTP server did not become ready')
            for name in suites:
                print('RUN ' + name, flush=True)
                began = time.monotonic()
                with (result_dir / (name + '.log')).open('w', encoding='utf-8') as log:
                    try:
                        completed = subprocess.run(
                            [sys.executable, '-X', 'utf8', str(workspace / 'prototypes' / name)],
                            cwd=workspace, stdout=log, stderr=subprocess.STDOUT, timeout=300,
                        )
                        code = completed.returncode
                    except subprocess.TimeoutExpired:
                        log.write('\nTIMEOUT after 300 seconds\n')
                        code = 124
                results.append({'suite': name, 'exit_code': code, 'seconds': round(time.monotonic() - began, 2)})
                print(('PASS ' if code == 0 else 'FAIL ') + name, flush=True)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        unchanged = source_hashes(release) == before
        report = {
            'hostname': socket.gethostname(), 'release': release.name,
            'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
            'suite': args.suite, 'results': results, 'release_unchanged': unchanged,
            'passed': len(results) == len(suites) and all(r['exit_code'] == 0 for r in results) and unchanged,
            'limitations': ['Prototype fixtures only; no real authentication, payment, SMS or cross-role backend',
                            'Headless Linux tests do not accept Windows native window stacking'],
        }
        (result_dir / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('REPORT ' + str(result_dir / 'summary.json'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
