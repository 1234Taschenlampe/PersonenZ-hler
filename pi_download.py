import sys

from pi_connection import connect


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: pi_download.py REMOTE_PATH LOCAL_PATH", file=sys.stderr)
        return 2
    remote_path, local_path = sys.argv[1:]
    client = connect()
    try:
        with client.open_sftp() as sftp:
            sftp.get(remote_path, local_path)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
