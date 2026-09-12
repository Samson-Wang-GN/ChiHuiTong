#!/usr/bin/env python3
"""Read-only aggregate health, without job payloads or recipient details."""

import json
from pathlib import Path
import socket
import subprocess

ROOT = Path('/home/ubuntu/ChiHuiTong')
if socket.gethostname() != 'VM-0-12-ubuntu':
    raise SystemExit('Only authorized server')
command = ['/usr/lib/postgresql/16/bin/psql', '-h', str(ROOT/'runtime/pgsocket'), '-p', '55432', '-d', 'chihuitong_acceptance', '-Atc']
location = subprocess.run(command+['SHOW data_directory'], check=True, capture_output=True, text=True, timeout=20).stdout.strip()
if Path(location).resolve() != ROOT/'runtime/postgres':
    raise SystemExit('Unexpected database instance')
query = "SELECT COALESCE(json_agg(x),'[]'::json) FROM (SELECT kind,status,last_error_code,count(*) AS count FROM chihuitong_outbox GROUP BY kind,status,last_error_code ORDER BY kind,status,last_error_code) x"
result = subprocess.run(command+[query], check=True, capture_output=True, text=True, timeout=20)
print(json.dumps(json.loads(result.stdout), ensure_ascii=False))
