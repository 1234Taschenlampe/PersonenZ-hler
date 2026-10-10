from pathlib import Path
import subprocess

import pytest

from visitor_counter.service_manager import ServiceActionError, ServiceManager


def test_service_manager_rejects_unapproved_action() -> None:
    manager = ServiceManager(admin_helper=Path("/missing"))
    with pytest.raises(ServiceActionError, match="Nicht erlaubte"):
        manager.action("enable")


def test_service_unit_name_is_not_interpolated_through_a_shell() -> None:
    manager = ServiceManager(unit="personenzaehler.service")
    command = manager._systemctl("show", manager.unit)  # noqa: SLF001
    assert command == ["systemctl", "show", "personenzaehler.service"]


@pytest.mark.parametrize("action", ["start", "restart", "stop"])
def test_explicit_user_start_clears_restart_limit(action: str, monkeypatch) -> None:
    monkeypatch.setattr("visitor_counter.service_manager.os.name", "posix")
    monkeypatch.setattr("visitor_counter.service_manager.shutil.which", lambda _: "/bin/systemctl")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "active\nrunning\n", "")

    manager = ServiceManager(user_service=True, runner=runner)
    manager.action(action)
    actions = [command[2] for command in calls]
    assert actions == (["stop", "show"] if action == "stop" else ["reset-failed", action, "show"])
