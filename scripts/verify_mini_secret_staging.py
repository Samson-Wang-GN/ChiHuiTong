#!/usr/bin/env python3
"""Isolated synthetic tests for the private credential staging helper."""
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'mini_staging', Path(__file__).with_name('stage-mini-customer-secret.py')
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StagingTests(unittest.TestCase):
    def test_stage_is_private_and_scope_is_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'pending.json'
            data = {'appid': 'wx1111111111111111', 'secret': 'syntheticsecret123', 'phone': '13900000101'}
            config = {'CHT_DB_NAME': 'chihuitong_acceptance', 'CHT_PHONE_INDEX_KEY': 'synthetic-key'}
            module.stage(data, config, target)
            result = json.loads(target.read_text())
            expected = hmac.new(b'synthetic-key', b'phone:13900000101', hashlib.sha256).hexdigest()
            self.assertEqual(result['allowed_index'], expected)
            self.assertNotIn(data['phone'], target.read_text())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                module.stage(data, config, target)
            self.assertEqual(json.loads(target.read_text()), result)

    def test_invalid_input_and_nonacceptance_database_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'pending.json'
            data = {'appid': 'wx1111111111111111', 'secret': 'syntheticsecret123', 'phone': '13900000101'}
            config = {'CHT_DB_NAME': 'production', 'CHT_PHONE_INDEX_KEY': 'synthetic-key'}
            with self.assertRaises(ValueError):
                module.stage(data, config, target)
            self.assertFalse(target.exists())
            config['CHT_DB_NAME'] = 'chihuitong_acceptance'
            data['phone'] = 'invalid'
            with self.assertRaises(ValueError):
                module.stage(data, config, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    if socket.gethostname() != 'VM-0-12-ubuntu':
        raise SystemExit('只能在指定开发服务器运行')
    unittest.main()
