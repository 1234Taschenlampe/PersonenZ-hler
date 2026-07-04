import os
import sys

import paramiko


HOST = os.environ.get("PI_HOST", "192.168.179.25")
USER = os.environ.get("PI_USER", "raspibob")
PASSWORD = os.environ["PI_PASS"]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: pi_download.py REMOTE_PATH LOCAL_PATH", file=sys.stderr)
        return 2
    remote_path, local_path = sys.argv[1:]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST,
        username=USER,
        password=PASSWORD,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    try:
        with client.open_sftp() as sftp:
            sftp.get(remote_path, local_path)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
