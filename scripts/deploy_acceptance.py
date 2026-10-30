#!/usr/bin/env python3
"""Explicitly authorized HTTPS acceptance deployment; no public new port, no real data."""

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path('/home/ubuntu/ChiHuiTong')
HOST = 'dev-public.chihui-ai.com'
PORT = 18243
CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-src blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
PG = Path('/usr/lib/postgresql/16/bin')
RUNTIME = ROOT / 'runtime' / 'acceptance'
# This server uses a regular file in sites-enabled, not the usual symlink.
SITE = Path('/etc/nginx/sites-enabled/study-system')
INCLUDE = Path('/etc/nginx/chihuitong-acceptance.locations.conf')
SERVICES = ['chihui-public.service', 'study-system-web.service', 'study-system-syncthing.service', 'nginx.service']


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True, timeout=120, **kwargs)


def install(content, destination, *, mode='0644', group='root'):
    stage = RUNTIME / ('stage-' + secrets.token_hex(8))
    stage.write_text(content)
    run(['sudo','-n','install','-o','root','-g',group,'-m',mode,stage,destination])
    stage.unlink()


def main():
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() == 0:
        raise SystemExit('Only the approved development server as ubuntu')
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT / 'releases' or len(release.name) != 40:
        raise SystemExit('Only an immutable verified release')
    os.umask(0o077)
    RUNTIME.mkdir(exist_ok=True, parents=True)
    import fcntl
    lock = (RUNTIME / 'deploy.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = {s: run(['systemctl','is-active',s], capture_output=True).stdout.strip() for s in SERVICES}
    existing = subprocess.run(['systemctl','is-active','chihuitong-acceptance.service'],capture_output=True,text=True).returncode == 0
    if not existing:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',PORT))
    runtime_config = RUNTIME / 'environment.json'
    if not runtime_config.exists():
        cfg = {'CHT_SECRET_KEY':secrets.token_urlsafe(48), 'CHT_FIELD_KEYS':base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), 'CHT_PHONE_INDEX_KEY':secrets.token_urlsafe(48), 'CHT_ACCEPTANCE_PROXY_TOKEN':secrets.token_urlsafe(48), 'CHT_ACCEPTANCE_ENABLED':'true', 'CHT_ENVIRONMENT':'development', 'CHT_DB_NAME':'chihuitong_acceptance', 'CHT_DB_USER':'ubuntu', 'CHT_DB_HOST':str(ROOT/'runtime'/'pgsocket'), 'CHT_DB_PORT':'55432', 'CHT_ALLOWED_HOSTS':HOST+',localhost,127.0.0.1', 'CHT_PRIVATE_STORAGE':str(RUNTIME/'private-files'), 'CHT_SMS_BACKEND':'chihuitong.acceptance.AcceptanceSMS', 'CHT_WECHAT_PAY_ENABLED':'false', 'PYTHONDONTWRITEBYTECODE':'1'}
        runtime_config.write_text(json.dumps(cfg))
    cfg = json.loads(runtime_config.read_text())
    if cfg['CHT_DB_NAME'] != 'chihuitong_acceptance' or cfg['CHT_WECHAT_PAY_ENABLED'] != 'false':
        raise SystemExit('Unexpected acceptance configuration; refusing overwrite')
    # REQ-045 explicitly authorizes virtual success, never live payment/SMS.
    cfg['CHT_ACCEPTANCE_SIMULATED_EXTERNALS'] = 'true'
    runtime_config.write_text(json.dumps(cfg))
    envfile = RUNTIME/'service.env'
    envfile.write_text('\n'.join(f'{k}={v}' for k,v in cfg.items())+'\n')
    env = dict(os.environ, **cfg)
    dbargs = ['-h',cfg['CHT_DB_HOST'],'-p','55432']
    location = run([PG/'psql',*dbargs,'-d','postgres','-Atc','SHOW data_directory'], capture_output=True).stdout.strip()
    if Path(location).resolve() != ROOT/'runtime'/'postgres':
        raise SystemExit('Wrong PostgreSQL instance')
    exists = run([PG/'psql',*dbargs,'-d','postgres','-Atc',"SELECT 1 FROM pg_database WHERE datname='chihuitong_acceptance'"],capture_output=True).stdout.strip()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if exists:
        run([PG/'pg_dump',*dbargs,'-Fc','-f',RUNTIME/f'before-{stamp}.dump',cfg['CHT_DB_NAME']])
    else:
        run([PG/'createdb',*dbargs,cfg['CHT_DB_NAME']])
    python=ROOT/'.venv-backend'/'bin'/'python'
    for command in [['migrate','--noinput'],['initialize_configuration'],['seed_acceptance'],['initialize_simulation'],['check']]:
        run([python,'manage.py',*command], cwd=release/'backend', env=env)
    creds_path = RUNTIME/'access.json'
    if not creds_path.exists():
        creds_path.write_text(json.dumps({'username':'acceptance','password':secrets.token_urlsafe(24)}))
    creds=json.loads(creds_path.read_text())
    hashed=run(['openssl','passwd','-6','-stdin'],input=creds['password']+'\n',capture_output=True).stdout.strip()
    install(creds['username']+':'+hashed+'\n','/etc/nginx/chihuitong-acceptance.htpasswd',mode='0640',group='www-data')
    location_text='''# Dedicated synthetic acceptance route. Existing routes are unchanged.
location = /chihuitong { return 302 /chihuitong/; }
location ^~ /chihuitong/ {
    auth_basic "ChiHuiTong acceptance";
    auth_basic_user_file /etc/nginx/chihuitong-acceptance.htpasswd;
    proxy_pass http://127.0.0.1:18243/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-CHT-Acceptance "PROXY_TOKEN";
    proxy_set_header Authorization $http_x_cht_authorization;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    client_max_body_size 10m;
    access_log off;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy no-referrer always;
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header Content-Security-Policy "{CSP}" always;
}
'''.replace('PROXY_TOKEN',cfg['CHT_ACCEPTANCE_PROXY_TOKEN']).replace('{CSP}', CSP)
    old_site=run(['sudo','-n','cat',SITE],capture_output=True).stdout
    needle='    server_name dev-public.chihui-ai.com;'
    directive=f'    include {INCLUDE};'
    inactive = Path('/etc/nginx/sites-available/study-system')
    if inactive.exists() and inactive.resolve() != SITE.resolve():
        inactive_text = run(['sudo','-n','cat',inactive],capture_output=True).stdout
        if directive + '\n' in inactive_text:
            # Remove only our earlier include from the inactive file; preserve all other bytes.
            install(inactive_text.replace(directive + '\n','',1),inactive)
    if needle not in old_site or 'listen 443 ssl' not in old_site:
        raise SystemExit('Unexpected Nginx site; manual review required')
    backup=RUNTIME/f'nginx-before-{stamp}.conf'
    backup.write_text(old_site)
    old_include=run(['sudo','-n','cat',INCLUDE],capture_output=True).stdout if INCLUDE.exists() else None
    install(location_text,INCLUDE,mode='0640',group='www-data')
    changed=directive not in old_site
    if changed:
        current=run(['sudo','-n','cat',SITE],capture_output=True).stdout
        if current!=old_site: raise SystemExit('Concurrent site edit detected')
        install(old_site.replace(needle,needle+'\n'+directive,1),SITE)
    try:
        run(['sudo','-n','nginx','-t'])
    except subprocess.CalledProcessError:
        if changed: install(old_site,SITE)
        if old_include is not None: install(old_include,INCLUDE,mode='0640',group='www-data')
        raise
    base=f'''[Unit]
Description=ChiHuiTong synthetic backend acceptance
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory={release}/backend
EnvironmentFile={envfile}
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
'''
    unit=base+f'''ExecStart={ROOT}/.venv-backend/bin/gunicorn config.wsgi:application --bind 127.0.0.1:{PORT} --workers 2 --timeout 60 --access-logfile /dev/null
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
'''
    install(unit,'/etc/systemd/system/chihuitong-acceptance.service')
    install(base+f'Type=oneshot\nExecStart={python} manage.py run_worker --limit 50\n','/etc/systemd/system/chihuitong-acceptance-worker.service')
    install('[Unit]\nDescription=ChiHuiTong acceptance tasks\n[Timer]\nOnBootSec=120\nOnUnitActiveSec=60\nUnit=chihuitong-acceptance-worker.service\n[Install]\nWantedBy=timers.target\n','/etc/systemd/system/chihuitong-acceptance-worker.timer')
    run(['sudo','-n','systemctl','daemon-reload'])
    run(['sudo','-n','systemctl','enable','--now','chihuitong-acceptance.service','chihuitong-acceptance-worker.timer'])
    run(['sudo','-n','systemctl','restart','chihuitong-acceptance.service'])
    run(['sudo','-n','systemctl','reload','nginx'])
    after={s:run(['systemctl','is-active',s],capture_output=True).stdout.strip() for s in SERVICES}
    if after!=before:raise SystemExit('Shared service state changed; investigate')
    report={'commit':release.name,'host':socket.gethostname(),'url':f'https://{HOST}/chihuitong/','services_before':before,'services_after':after,'nginx_backup':str(backup),'original_site_sha256':hashlib.sha256(old_site.encode()).hexdigest(),'acceptance_port':PORT}
    (RUNTIME/'deployment.json').write_text(json.dumps(report,indent=2))
    handoff='齿慧通后端验收（仅合成数据）\n入口：https://'+HOST+'/chihuitong/\n入口用户名：'+creds['username']+'\n入口口令：'+creds['password']+'\n\n此口令仅用于第一层访问保护；请勿提交到Git或转发给无关人员。\n各角色：platform 13800000001；resource 13800000002；channel 13800000003；clinic 13800000004。\n点击获取验证码后，点击查看测试短信箱；不接收真实短信。\n'
    (RUNTIME/'access-handoff.txt').write_text(handoff)
    print('DEPLOYED='+report['url'])


if __name__=='__main__':
    main()
