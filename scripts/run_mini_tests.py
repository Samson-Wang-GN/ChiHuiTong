#!/usr/bin/env python3
"""Build/test native sources only on the designated host, in a disposable copy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ROOT = Path('/home/ubuntu/ChiHuiTong')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock-only', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() == 0:
        raise SystemExit('只能在指定开发服务器以ubuntu身份运行')
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT / 'releases' or len(release.name) != 40:
        raise SystemExit('必须使用已校验提交快照')
    os.umask(0o077)
    report = ROOT / 'test-results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + release.name[:12] + '-mini')
    workspace = report / 'workspace'
    shutil.copytree(release / 'mini-programs', workspace)
    node = ROOT / 'runtime/node-download/node-v22.23.2-linux-x64/bin'
    env = dict(os.environ, PATH=str(node) + ':' + os.environ['PATH'], CHT_SOURCE_COMMIT=release.name)
    baseline = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (release / 'mini-programs').rglob('*') if p.is_file()}
    summary = {'commit': release.name, 'steps': [], 'passed': False, 'native_wechat_tested': False}
    print('MINI_REPORT=' + str(report), flush=True)
    try:
        commands = [('dependencies', [str(node / 'npm'), 'install' if args.lock_only else 'ci', '--ignore-scripts', '--no-fund', '--no-audit'])]
        if not args.lock_only:
            commands += [('build', [str(node / 'node'), 'build.mjs']), ('unit', [str(node / 'node'), '--test', 'tests/native.test.cjs'])]
        for name, command in commands:
            with (report / (name + '.log')).open('w') as log:
                result = subprocess.run(command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            summary['steps'].append({'name': name, 'exit_code': result.returncode})
            print(name + ': ' + str(result.returncode), flush=True)
            if result.returncode:
                raise RuntimeError('检查日志：' + str(report / (name + '.log')))
        summary['passed'] = True
    finally:
        summary['release_unchanged'] = all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == v for p, v in baseline.items())
        (report / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
