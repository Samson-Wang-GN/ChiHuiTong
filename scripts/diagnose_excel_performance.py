#!/usr/bin/env python3
"""Server-only stage timings; disposable synthetic DB, no acceptance writes."""

import base64
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path('/home/ubuntu/ChiHuiTong')
PG = Path('/usr/lib/postgresql/16/bin')


def main():
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() != 1000:
        raise SystemExit('Only approved development server as ubuntu')
    release = (ROOT / 'current').resolve()
    if release.parent != ROOT / 'releases' or len(release.name) != 40:
        raise SystemExit('Expected immutable release')
    os.umask(0o077)
    report = ROOT / 'test-results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-excel-performance')
    report.mkdir()
    dbname = 'chihuitong_diagnostic_' + secrets.token_hex(6)
    dbargs = ['-h', str(ROOT / 'runtime/pgsocket'), '-p', '55432']

    def run(args, **kwargs):
        return subprocess.run([str(arg) for arg in args], check=True, text=True, timeout=120, **kwargs)

    location = run([PG / 'psql', *dbargs, '-d', 'postgres', '-Atc', 'SHOW data_directory'], capture_output=True).stdout.strip()
    if Path(location).resolve() != ROOT / 'runtime/postgres':
        raise SystemExit('Unexpected PostgreSQL instance')
    os.environ.update(
        DJANGO_SETTINGS_MODULE='config.settings', CHT_ENVIRONMENT='test',
        CHT_ACCEPTANCE_ENABLED='false', CHT_ACCEPTANCE_SIMULATED_EXTERNALS='false',
        CHT_SECRET_KEY=secrets.token_urlsafe(48),
        CHT_FIELD_KEYS=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        CHT_PHONE_INDEX_KEY=secrets.token_urlsafe(48), CHT_DB_NAME=dbname,
        CHT_DB_USER='ubuntu', CHT_DB_PASSWORD='', CHT_DB_HOST=dbargs[1], CHT_DB_PORT='55432',
        CHT_ALLOWED_HOSTS='testserver,localhost', CHT_PRIVATE_STORAGE=str(report / 'private-files'),
        CHT_SMS_BACKEND='chihuitong.integrations.sms.DisabledSMS', CHT_WECHAT_PAY_ENABLED='false',
        PYTHONDONTWRITEBYTECODE='1',
    )
    summary = {'source_commit': release.name, 'passed': False, 'cases': [],
               'scope': 'APIClient synchronous processing; no worker, network or browser'}
    run([PG / 'createdb', *dbargs, dbname])
    print('REPORT=' + str(report / 'summary.json'), flush=True)
    try:
        with (report / 'setup.log').open('w') as log:
            run([ROOT / '.venv-backend/bin/python', release / 'backend/manage.py', 'migrate', '--noinput'], stdout=log, stderr=subprocess.STDOUT)
        sys.path.insert(0, str(release / 'backend'))
        import django
        django.setup()
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import connection
        from openpyxl import Workbook
        from chihuitong.models import ImportBatch, Outbox
        from chihuitong.tests.support import actor_fixture, api_client

        actor = actor_fixture('broker', '13900000002')
        client = api_client(actor)

        def timed(callback):
            counters = {'queries': 0, 'customer_queries': 0, 'sql_seconds': 0.0}

            def execute(executor, sql, params, many, context):
                counters['queries'] += 1
                if '"chihuitong_customer"' in sql:
                    counters['customer_queries'] += 1
                started = time.perf_counter()
                try:
                    return executor(sql, params, many, context)
                finally:
                    counters['sql_seconds'] += time.perf_counter() - started

            started = time.perf_counter()
            with connection.execute_wrapper(execute):
                result = callback()
            counters['seconds'] = round(time.perf_counter() - started, 6)
            counters['sql_seconds'] = round(counters['sql_seconds'], 6)
            if hasattr(result, 'status_code'):
                assert result.status_code in {200, 201}, result.status_code
                result = result.json()
            return result, counters

        for row_count in [2, 100, 1000, 10000]:
            for repetition in range(3):
                book = Workbook(write_only=True)
                sheet = book.create_sheet('Customers')
                sheet.append(['name', 'phone', 'quantity'])
                for number in range(row_count):
                    sheet.append(['Synthetic ' + str(number), str(13910000000 + number), 1])
                buffer = io.BytesIO()
                book.save(buffer)
                data = buffer.getvalue()
                case = {'rows': row_count, 'repetition': repetition + 1, 'bytes': len(data)}
                uploaded, case['upload_api'] = timed(lambda: client.post('/api/v1/files', {
                    'file': SimpleUploadedFile('synthetic.xlsx', data), 'purpose': 'sales_excel'}, format='multipart'))
                batch, case['enqueue_api'] = timed(lambda: client.post('/api/v1/imports', {
                    'asset_id': uploaded['id']}, format='json', HTTP_IDEMPOTENCY_KEY=secrets.token_hex(16)))
                assert batch['status'] == 'mapping'
                detail, case['preview_api'] = timed(lambda: client.get('/api/v1/imports/' + batch['id']))
                assert detail['status'] == 'mapping'
                suggestion = detail['recommendation']
                mapped, case['mapping_api'] = timed(lambda: client.post('/api/v1/imports/' + batch['id'] + '/mapping', {
                    'version': detail['version'], 'sheet': suggestion['sheet'], 'header_row': suggestion['header_row'],
                    'mapping': suggestion['mapping'], 'quantity_mode': 'column',
                }, format='json', HTTP_IDEMPOTENCY_KEY=secrets.token_hex(16)))
                assert mapped['status'] == 'validated'
                validated, case['result_api'] = timed(lambda: client.get('/api/v1/imports/' + batch['id']))
                assert (validated['status'], validated['total_rows'], validated['error_rows']) == ('validated', row_count, 0)
                assert ImportBatch.objects.get(pk=batch['id']).rows.count() == row_count
                summary['cases'].append(case)
                print(json.dumps(case), flush=True)
        assert not Outbox.objects.filter(kind__in=['excel.inspect', 'excel.validate']).exists()
        summary['passed'] = True
    finally:
        if 'django.db' in sys.modules:
            from django.db import connections
            connections.close_all()
        # Delete only the exact isolated database created by this invocation.
        run([PG / 'dropdb', *dbargs, dbname])
        summary['disposable_database_removed'] = True
        (report / 'summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
