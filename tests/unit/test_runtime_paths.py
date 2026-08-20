from pathlib import Path

from visitor_counter.runtime_paths import RuntimePaths


def test_development_paths_stay_inside_project(tmp_path: Path) -> None:
    paths = RuntimePaths.discover(tmp_path, environ={}, home=tmp_path / "home")
    assert paths.config_file == tmp_path / "config" / "config.yaml"
    assert paths.data_dir == tmp_path / "data"
    assert paths.license_file == tmp_path / "config" / "license.json"
    assert paths.state_dir == tmp_path / "home" / ".local" / "state" / "personenzaehler"


def test_system_paths_follow_linux_filesystem_layout(tmp_path: Path) -> None:
    paths = RuntimePaths.discover(
        tmp_path, system_layout=True, environ={}, home=tmp_path / "home"
    )
    assert paths.config_file == Path("/etc/personenzaehler/config.yaml")
    assert paths.data_dir == Path("/var/lib/personenzaehler")
    assert paths.log_dir == Path("/var/log/personenzaehler")
    assert paths.model_dir == Path("/var/lib/personenzaehler/models")


def test_environment_can_redirect_every_mutable_path(tmp_path: Path) -> None:
    environment = {
        "PERSONENZAEHLER_CONFIG_FILE": str(tmp_path / "c.yaml"),
        "PERSONENZAEHLER_DATA_DIR": str(tmp_path / "data-x"),
        "PERSONENZAEHLER_LOG_DIR": str(tmp_path / "log-x"),
        "PERSONENZAEHLER_CACHE_DIR": str(tmp_path / "cache-x"),
        "PERSONENZAEHLER_STATE_DIR": str(tmp_path / "state-x"),
    }
    paths = RuntimePaths.discover(tmp_path, environ=environment, home=tmp_path)
    assert paths.config_file == tmp_path / "c.yaml"
    assert paths.data_dir == tmp_path / "data-x"
    assert paths.state_dir == tmp_path / "state-x"
