from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_app_help_does_not_import_gui_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")

    completed = subprocess.run(
        [sys.executable, "-m", "visitor_counter.app", "--help"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert "--test-global-counter" in completed.stdout
