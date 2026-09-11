"""Synthetic, disposable restore drill. Never restores into an existing database."""

import copy
import hashlib
import json
import os
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections, transaction
from psycopg import sql

from chihuitong.crypto import cipher, digest
from chihuitong.models import AuditEvent, Customer


class Command(BaseCommand):
    help = (
        "仅指定测试服务器：新建合成源库和恢复库，验证备份、密文解密及审计保护，结束清理本次临时库"
    )

    def handle(self, *args, **options):
        root = Path("/home/ubuntu/ChiHuiTong")
        workspace = Path.cwd().resolve()
        config = connections["default"].settings_dict
        if (
            socket.gethostname() != "VM-0-12-ubuntu"
            or settings.ENVIRONMENT != "test"
            or not workspace.is_relative_to(root / "test-results")
            or config["HOST"] != str(root / "runtime/pgsocket")
            or str(config["PORT"]) != "55432"
        ):
            raise CommandError("备份验证仅允许指定服务器独立测试环境")
        with connections["default"].cursor() as cursor:
            cursor.execute("SHOW data_directory")
            if Path(cursor.fetchone()[0]).resolve() != root / "runtime/postgres":
                raise CommandError("拒绝接触非本项目数据库实例")
        nonce = uuid.uuid4().hex[:16]
        names = ["cht_backup_probe_" + nonce, "cht_restore_probe_" + nonce]
        report = workspace.parent / "backup-restore"
        report.mkdir(mode=0o700)
        created = []
        aliases = []
        summary = {"passed": False, "temporary_databases": names, "removed_databases": []}
        try:
            for index, name in enumerate(names):
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                            sql.Identifier(name)
                        )
                    )
                created.append(name)
                alias = "backup_probe_" + str(index)
                connections.databases[alias] = {**copy.deepcopy(config), "NAME": name}
                aliases.append(alias)
            source, target = aliases
            call_command("migrate", database=source, interactive=False, verbosity=0)
            customer = Customer.objects.using(source).create(
                name="合成备份客户",
                phone="13900000991",
                phone_index=digest("13900000991", purpose="phone"),
                profile={"occupation": "合成数据"},
            )
            audit = AuditEvent.objects.using(source).create(
                object_type="customer",
                object_id=customer.id,
                action="synthetic.backup_check",
                metadata={"synthetic": True},
            )
            connections[source].close()
            pg = Path("/usr/lib/postgresql/16/bin")
            shared = ["-h", str(root / "runtime/pgsocket"), "-p", "55432", "-U", "ubuntu"]
            archive = report / "synthetic.pgdump"
            with (report / "postgres.log").open("w") as log:
                subprocess.run(
                    [
                        pg / "pg_dump",
                        *shared,
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--file",
                        archive,
                        names[0],
                    ],
                    check=True,
                    timeout=120,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                subprocess.run(
                    [
                        pg / "pg_restore",
                        *shared,
                        "--exit-on-error",
                        "--single-transaction",
                        "--no-owner",
                        "--no-acl",
                        "--dbname",
                        names[1],
                        archive,
                    ],
                    check=True,
                    timeout=120,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            restored = Customer.objects.using(target).get(pk=customer.id)
            if (restored.name, restored.phone, restored.profile) != (
                customer.name,
                customer.phone,
                customer.profile,
            ):
                raise CommandError("恢复后的合成加密字段不一致")
            protected = False
            try:
                with transaction.atomic(using=target):
                    AuditEvent.objects.using(target).filter(pk=audit.pk).update(
                        action="synthetic.tamper"
                    )
            except DatabaseError:
                protected = True
            if not protected:
                raise CommandError("恢复后的审计防篡改触发器未生效")
            original = report / "synthetic-file.encrypted"
            recovered = report / "restored-file.encrypted"
            payload = b"synthetic backup attachment, no business data"
            original.write_bytes(cipher().encrypt(payload))
            shutil.copy2(original, recovered)
            if cipher().decrypt(recovered.read_bytes()) != payload:
                raise CommandError("加密附件恢复失败")
            summary.update(
                passed=True,
                encrypted_fields_verified=True,
                audit_trigger_verified=True,
                encrypted_file_verified=True,
                dump_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            )
        finally:
            for alias in aliases:
                connections[alias].close()
            for name in reversed(created):
                # Only names successfully created by this invocation; never default/test/shared databases.
                if name not in names or not name.endswith(nonce):
                    raise CommandError("临时库名称不匹配，停止清理")
                with connections["default"].cursor() as cursor:
                    cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                summary["removed_databases"].append(name)
            (report / "summary.json").write_text(json.dumps(summary, indent=2))
            os.chmod(report / "summary.json", 0o600)
        self.stdout.write(
            "BACKUP_RESTORE_PASSED: synthetic database, encrypted fields/files, audit trigger; temporary databases removed"
        )
