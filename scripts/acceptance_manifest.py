#!/usr/bin/env python3
"""Read-only acceptance record identity digest; never output identities or business contents."""

import hashlib
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
tables = ['account','appointment','clinicbill','partnerbill','salesorder','card','customer','benefit']
query = ' UNION ALL '.join("SELECT '"+table+"',id::text FROM chihuitong_"+table for table in tables)+' ORDER BY 1,2'
result = subprocess.run(command+[query], check=True, capture_output=True, timeout=20)
print(json.dumps({'records':len(result.stdout.splitlines()), 'sha256':hashlib.sha256(result.stdout).hexdigest()}))
