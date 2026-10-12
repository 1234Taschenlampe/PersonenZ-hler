import sqlite3

import pytest

from scripts.backup_installation import backup_database, private_copy


def test_sqlite_backup_contains_committed_wal_without_modifying_source(tmp_path):
    source = tmp_path / "source #counts.sqlite3"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE counts (inside INTEGER)")
        live.execute("INSERT INTO counts VALUES (7)")
        live.commit()
        target = tmp_path / "private-backup/counts.sqlite3"
        assert backup_database(source, target)["integrity"] == "ok"
        with sqlite3.connect(target) as copy:
            assert copy.execute("SELECT inside FROM counts").fetchone()[0] == 7
        assert live.execute("SELECT inside FROM counts").fetchone()[0] == 7


def test_private_backup_refuses_symlinks(tmp_path):
    source = tmp_path / "source"
    source.write_text("private fixture")
    link = tmp_path / "link"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        private_copy(link, tmp_path / "destination")
