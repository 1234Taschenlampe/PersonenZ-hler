from __future__ import annotations

import getpass
import os
from pathlib import Path

import paramiko


def connect() -> paramiko.SSHClient:
    host = os.environ.get("PI_HOST", "").strip()
    if not host:
        raise RuntimeError("PI_HOST must be set explicitly.")
    user = os.environ.get("PI_USER", getpass.getuser()).strip()
    port = int(os.environ.get("PI_PORT", "22"))
    known_hosts = Path(os.environ.get("PI_KNOWN_HOSTS", "~/.ssh/known_hosts")).expanduser()
    if not known_hosts.is_file():
        raise RuntimeError(f"Known-hosts file does not exist: {known_hosts}")
    key_file_value = os.environ.get("PI_KEY_FILE", "").strip()
    key_file = Path(key_file_value).expanduser() if key_file_value else None
    if key_file is not None and not key_file.is_file():
        raise RuntimeError(f"SSH private key does not exist: {key_file}")
    allow_password = os.environ.get("PI_ALLOW_PASSWORD_AUTH") == "1"
    password = os.environ.get("PI_PASS") if allow_password else None

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        key_filename=str(key_file) if key_file else None,
        password=password,
        look_for_keys=True,
        allow_agent=True,
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
    )
    return client
