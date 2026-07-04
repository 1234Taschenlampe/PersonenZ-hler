from __future__ import annotations

import importlib.util

import pytest


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")
def test_gui_module_imports() -> None:
    import visitor_counter.gui as gui

    assert gui.MainWindow is not None
