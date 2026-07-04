import os
import sys

import paramiko


HOST = os.environ.get("PI_HOST", "192.168.179.25")
USER = os.environ.get("PI_USER", "raspibob")
PASSWORD = os.environ["PI_PASS"]


def main() -> int:
    script = sys.stdin.read()
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
        stdin, stdout, stderr = client.exec_command("bash -s", get_pty=False, timeout=180)
        stdin.write(script)
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if out:
            sys.stdout.buffer.write(out.encode("utf-8", "replace"))
        if err:
            sys.stderr.buffer.write(err.encode("utf-8", "replace"))
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
