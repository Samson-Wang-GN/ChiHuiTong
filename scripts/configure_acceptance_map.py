#!/usr/bin/env python3
"""Install the supplied map key after live preflight; never print secrets/URLs."""

import base64
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path('/home/ubuntu/ChiHuiTong')
RUNTIME = ROOT / 'runtime/acceptance'


def main():
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() == 0:
        raise SystemExit('Only approved server as ubuntu')
    os.umask(0o077)
    incoming = RUNTIME / 'map-key-input.env'
    incoming.chmod(0o600)
    lock = (RUNTIME / 'deploy.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = ROOT / 'test-results' / (stamp + '-map-activation')
    report.mkdir()
    result = {'passed': False, 'public_place_only': True, 'business_records_modified': False}
    print('MAP_REPORT=' + str(report / 'summary.json'), flush=True)

    def run(args):
        return subprocess.run(args, check=True, text=True, capture_output=True, timeout=35)

    def replace(path, content):
        fd, name = tempfile.mkstemp(prefix='map-config-', dir=RUNTIME)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    try:
        lines = [line.strip() for line in incoming.read_text(encoding='utf-8-sig').splitlines()
                 if line.strip() and not line.lstrip().startswith('#')]
        if len(lines) != 1 or not lines[0].startswith('CHT_TENCENT_MAP_KEY='):
            raise ValueError('Expected only map key')
        key = lines[0].split('=', 1)[1].strip()
        if not re.fullmatch(r'[A-Za-z0-9-]{20,160}', key):
            raise ValueError('Invalid key format')
        cfg_path, env_path = RUNTIME / 'environment.json', RUNTIME / 'service.env'
        cfg = json.loads(cfg_path.read_text())
        if cfg.get('CHT_DB_NAME') != 'chihuitong_acceptance' or cfg.get('CHT_WECHAT_PAY_ENABLED') != 'false':
            raise ValueError('Unexpected environment')
        directory = Path(run(['systemctl', 'show', 'chihuitong-acceptance.service', '-p', 'WorkingDirectory', '--value']).stdout.strip())
        if directory.name != 'backend' or directory.parent.parent != ROOT / 'releases':
            raise ValueError('Unexpected running source')
        result['application_commit'] = directory.parent.name
        os.environ.update(cfg)
        os.environ.update(CHT_TENCENT_MAP_KEY=key, DJANGO_SETTINGS_MODULE='config.settings')
        sys.path.insert(0, str(directory))
        import django
        django.setup()
        from chihuitong.integrations.tencent_map import geocode, static_map
        candidate = geocode('北京市海淀区中关村大街1号')
        result['geocode'] = {'passed': True, 'coordinate_system': candidate['coordinate_system']}
        picture = static_map(candidate['latitude'], candidate['longitude'], 16)
        (report / 'public-place-map.png').write_bytes(picture)
        result['static_map'] = {'passed': True, 'bytes': len(picture)}
        old_cfg, old_env = cfg_path.read_text(), env_path.read_text()
        for path in [cfg_path, env_path]:
            backup = RUNTIME / (path.name + '.before-map-' + stamp)
            shutil.copyfile(path, backup)
            backup.chmod(0o600)
        result['backup_suffix'] = '.before-map-' + stamp
        updated = dict(cfg, CHT_TENCENT_MAP_KEY=key)
        env_lines = [line for line in old_env.splitlines() if not line.startswith('CHT_TENCENT_MAP_KEY=')]
        try:
            replace(cfg_path, json.dumps(updated))
            replace(env_path, '\n'.join(env_lines + ['CHT_TENCENT_MAP_KEY=' + key]) + '\n')
            run(['sudo', '-n', 'systemctl', 'restart', 'chihuitong-acceptance.service'])
            creds = json.loads((RUNTIME / 'access.json').read_text())
            basic = base64.b64encode((creds['username'] + ':' + creds['password']).encode()).decode()
            request = urllib.request.Request('https://dev-public.chihui-ai.com/chihuitong/api/v1/health', headers={'Authorization': 'Basic ' + basic})
            healthy = False
            for _ in range(10):
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        healthy = response.status == 200
                    if healthy:
                        break
                except OSError:
                    time.sleep(.5)
            if not healthy:
                raise RuntimeError('Service health failed')
        except Exception:
            replace(cfg_path, old_cfg)
            replace(env_path, old_env)
            run(['sudo', '-n', 'systemctl', 'restart', 'chihuitong-acceptance.service'])
            result['configuration_rolled_back'] = True
            raise
        result['passed'] = True
    except Exception as error:
        # No traceback: upstream exceptions can include request URLs containing the key.
        result['error_code'] = getattr(error, 'code', type(error).__name__)
    finally:
        incoming.unlink(missing_ok=True)
        result['temporary_key_file_removed'] = True
        (report / 'summary.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
