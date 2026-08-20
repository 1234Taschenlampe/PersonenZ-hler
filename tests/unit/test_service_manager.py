from pathlib import Path

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
