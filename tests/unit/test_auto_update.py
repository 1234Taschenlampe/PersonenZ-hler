"""Offline regressions for the unattended GitHub updater."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "auto_update.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("personenzaehler_auto_update", SCRIPT)
assert spec and spec.loader
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@pytest.fixture
def auto_env(tmp_path, monkeypatch):
    for variable, directory in (
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_STATE_HOME", "state"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / directory))
    root = tmp_path / "app"
    root.mkdir()
    (root / ".git").mkdir()
    # The CI and release-safety gates are independently tested below.
    monkeypatch.setattr(updater.update_safety, "ci_approved", lambda _sha: (True, "ok"))
    monkeypatch.setattr(updater.update_safety, "preflight_candidate", lambda *_args: None)
    monkeypatch.setattr(updater.update_safety, "service_paths_correct",
                        lambda *_args: (True, "ok"))
    monkeypatch.setattr(updater.update_safety, "healthy_cameras_before_update", lambda: set())
    monkeypatch.setattr(updater.time, "localtime", lambda: SimpleNamespace(tm_hour=3))
    return root


def test_origin_is_exactly_pinned_to_original_repo():
    assert updater.allowed_origin(updater.EXPECTED_ORIGIN)
    assert updater.allowed_origin(updater.EXPECTED_ORIGIN + ".git")
    assert not updater.allowed_origin("https://github.com/other/PersonenZ-hler.git")
    assert not updater.allowed_origin(updater.EXPECTED_ORIGIN + "-injected.git")
    assert not updater.allowed_origin("https://github.com/1234Taschenlampe/other.git")


def test_operator_can_pause_updates_without_network(auto_env, monkeypatch):
    config_dir = Path(__import__("os").environ["XDG_CONFIG_HOME"]) / "personenzaehler"
    config_dir.mkdir(parents=True)
    (config_dir / "auto-update.paused").touch()
    monkeypatch.setattr(updater, "git", lambda *_args: pytest.fail("Git must not run"))
    assert updater.update(auto_env) == 0
    report = json.loads(
        (Path(__import__("os").environ["XDG_STATE_HOME"])
         / "personenzaehler/auto-update-status.json").read_text()
    )
    assert report["result"] == "paused"


def _stub_git(root, monkeypatch, *, dirty=False, remote=None, branch="main"):
    state = {"head": "a" * 40, "fetch": "b" * 40, "actions": []}

    def fake_git(_root, *args, **kwargs):
        state["actions"].append(args)
        if args[:3] == ("symbolic-ref", "--quiet", "--short"):
            return branch
        if args[:2] == ("remote", "get-url"):
            return updater.EXPECTED_ORIGIN + ".git" if remote is None else remote
        if args[:2] == ("status", "--porcelain"):
            return " M src/visitor_counter/counter.py" if dirty else ""
        if args[:2] == ("rev-parse", "HEAD"):
            return state["head"]
        if args[:2] == ("rev-parse", "FETCH_HEAD"):
            return state["fetch"]
        raise AssertionError(f"Unexpected git: {args}")

    monkeypatch.setattr(updater, "git", fake_git)
    return state


def _stub_run(state, monkeypatch):
    def fake_run(argv, *, cwd, timeout=120, env=None, capture=False):
        if argv[:3] == ["git", "-C", str(cwd)]:
            if "merge" in argv:
                state["head"] = state["fetch"]
            if "reset" in argv:
                state["head"] = "a" * 40
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(updater, "exec_checked", fake_run)


def test_dirty_checkout_blocks_auto_update_before_network(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch, dirty=True)
    monkeypatch.setattr(updater, "exec_checked", lambda *_args, **kwargs:
                        pytest.fail("Network must not be contacted"))
    assert updater.update(auto_env) == 1
    assert state["head"] == "a" * 40


def test_wrong_branch_or_remote_blocks_unattended_code(auto_env, monkeypatch):
    _stub_git(auto_env, monkeypatch, branch="feature/unstable")
    monkeypatch.setattr(updater, "exec_checked", lambda *_args, **kwargs:
                        pytest.fail("Should not download untrusted branch"))
    assert updater.update(auto_env) == 1


def test_check_only_fetches_but_does_not_install(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater, "installer", lambda *_args, **kwargs:
                        pytest.fail("Must not install during check-only"))
    assert updater.update(auto_env, check_only=True) == 0
    assert state["head"] == "a" * 40


def test_new_commit_installs_and_checks_services(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater, "service_running", lambda *_args: True)
    called = []
    monkeypatch.setattr(updater, "installer", lambda *args, **kwargs: called.append("install"))
    monkeypatch.setattr(updater.update_safety, "wait_for_recovery",
                        lambda *args, **kwargs: called.append("health"))
    assert updater.update(auto_env) == 0
    assert state["head"] == "b" * 40
    assert called == ["install", "health"]


def test_bad_install_rolls_back_without_touching_data(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater, "service_running", lambda *_args: True)
    installs = []

    def fake_installer(_root, *, rollback=False):
        installs.append(rollback)
        if not rollback:
            raise RuntimeError("new version broken")

    monkeypatch.setattr(updater, "installer", fake_installer)
    monkeypatch.setattr(updater.update_safety, "wait_for_recovery",
                        lambda *args, **kwargs: None)
    assert updater.update(auto_env) == 1
    assert state["head"] == "a" * 40
    assert installs == [False, True]
    report = json.loads(
        (Path(__import__("os").environ["XDG_STATE_HOME"])
         / "personenzaehler/auto-update-status.json").read_text()
    )
    assert report["result"] == "rolled_back"


def test_updater_timer_is_configured_by_source_installer():
    script = (SCRIPT.parent / "install_autostart.sh").read_text()
    assert "personenzaehler-update.timer" in script
    assert "OnBootSec=15min" in script
    assert "OnCalendar=*-*-* 03,09,15,21:00:00" in script
    assert "Persistent=true" in script
    assert "ExecStart=/usr/bin/python3 $PWD/scripts/auto_update.py" in script.replace('"', '')

def test_failing_ci_does_not_change_running_installation(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater.update_safety, "ci_approved",
                        lambda _sha: (False, "Unit test failed"))
    monkeypatch.setattr(updater, "installer",
                        lambda *_args, **kwargs: pytest.fail("Must not install"))
    assert updater.update(auto_env) == 0
    assert state["head"] == "a" * 40
    report = json.loads(
        (Path(__import__("os").environ["XDG_STATE_HOME"])
         / "personenzaehler/auto-update-status.json").read_text()
    )
    assert report["result"] == "blocked_ci"


def test_candidate_fails_before_merge_without_disrupting_services(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)

    def invalid_candidate(*_args):
        raise RuntimeError("Invalid shell syntax")

    monkeypatch.setattr(updater.update_safety, "preflight_candidate", invalid_candidate)
    assert updater.update(auto_env) == 1
    assert state["head"] == "a" * 40
    assert ("merge", "--ff-only", "b" * 40) not in state["actions"]


def test_old_install_path_is_rejected_before_merge(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater, "service_running", lambda *_args: True)
    monkeypatch.setattr(updater.update_safety, "service_paths_correct",
                        lambda *_args: (False, "Running PR18 service"))
    assert updater.update(auto_env) == 1
    assert state["head"] == "a" * 40

def test_daytime_only_checks_updates_without_restart(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater.time, "localtime", lambda: SimpleNamespace(tm_hour=14))
    monkeypatch.setattr(updater, "installer",
                        lambda *_args, **kwargs: pytest.fail("No install during presentations"))
    assert updater.update(auto_env) == 0
    assert state["head"] == "a" * 40
    report = json.loads(
        (Path(__import__("os").environ["XDG_STATE_HOME"])
         / "personenzaehler/auto-update-status.json").read_text()
    )
    assert report["result"] == "available"


def test_explicit_apply_now_overrides_quiet_hours_but_not_ci(auto_env, monkeypatch):
    state = _stub_git(auto_env, monkeypatch)
    _stub_run(state, monkeypatch)
    monkeypatch.setattr(updater.time, "localtime", lambda: SimpleNamespace(tm_hour=14))
    monkeypatch.setattr(updater, "service_running", lambda *_args: True)
    monkeypatch.setattr(updater, "installer", lambda *_args, **kwargs: None)
    monkeypatch.setattr(updater.update_safety, "wait_for_recovery",
                        lambda *args, **kwargs: None)
    assert updater.update(auto_env, apply_now=True) == 0
    assert state["head"] == "b" * 40
