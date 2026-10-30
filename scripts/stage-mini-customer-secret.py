#!/usr/bin/env python3
"""Receive private test credentials on stdin; never print their values or enable services."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import sys
import unicodedata

ROOT = Path('/home/ubuntu/ChiHuiTong')
RUNTIME = ROOT / 'runtime' / 'acceptance'


def main():
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() == 0:
        raise SystemExit('只能在指定开发服务器以ubuntu身份运行')
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT / 'releases' or len(release.name) != 40:
        raise SystemExit('必须使用已校验的提交快照')
    try:
        data = json.loads(sys.stdin.readline(4096))
        if set(data) != {'appid', 'secret', 'phone'}:
            raise ValueError()
        appid, secret = data['appid'], data['secret']
        phone = re.sub(r'[\s\-()]', '', unicodedata.normalize('NFKC', data['phone']).strip())
        if phone.startswith('+86'):
            phone = phone[3:]
        elif phone.startswith('0086'):
            phone = phone[4:]
        if not re.fullmatch(r'wx[a-fA-F0-9]{16}', appid):
            raise ValueError()
        if not re.fullmatch(r'[a-zA-Z0-9]{16,128}', secret):
            raise ValueError()
        if not re.fullmatch(r'1[3-9]\d{9}', phone):
            raise ValueError()
        config = json.loads((RUNTIME / 'environment.json').read_text())
        if config.get('CHT_DB_NAME') != 'chihuitong_acceptance':
            raise ValueError()
        index = hmac.new(config['CHT_PHONE_INDEX_KEY'].encode(), ('phone:' + phone).encode(), hashlib.sha256).hexdigest()
        staged = {'appid': appid, 'secret': secret, 'allowed_index': index}
        target = RUNTIME / 'mini-customer-pending.json'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(staged, file)
        print('安全录入完成；配置仅暂存，测试入口尚未启用。')
    except (ValueError, TypeError, KeyError, OSError):
        raise SystemExit('录入失败：请核对格式，或联系开发人员检查已有暂存配置。') from None


if __name__ == '__main__':
    main()
