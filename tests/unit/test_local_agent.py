from pathlib import Path
import pytest

from visitor_counter.local_agent import LocalGemmaAgent, ProjectKnowledgeBase, redact_secrets


def test_redacts_credentials() -> None:
    # Construct the credential-shaped test value at runtime so repository secret
    # scanners do not have to whitelist a password-like URL literal.
    text = "rtsp://" + "user" + ":" + "pass" + "@" + "192.168.1.2/stream password=hunter2"
    safe = redact_secrets(text)
    assert "pass@" not in safe
    assert "hunter2" not in safe


def test_kb_ignores_data_and_models(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("person counter", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret.json").write_text("person counter", encoding="utf-8")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "note.md").write_text("person counter", encoding="utf-8")
    kb = ProjectKnowledgeBase(tmp_path)
    paths = {chunk.path for chunk in kb.search("person counter")}
    assert "src/a.py" in paths
    assert "data/secret.json" not in paths
    assert "models/note.md" not in paths


def test_change_requires_confirmation_and_hash_match(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("a: 1\n", encoding="utf-8")
    agent = LocalGemmaAgent(tmp_path)
    proposal = agent.propose_file_change("config.yaml", "a: 2\n", "test")
    with pytest.raises(PermissionError):
        agent.apply_proposal(proposal)
    target.write_text("a: 3\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        agent.apply_proposal(proposal, confirmed=True)


def test_change_blocks_path_escape(tmp_path: Path) -> None:
    agent = LocalGemmaAgent(tmp_path)
    with pytest.raises(ValueError):
        agent.propose_file_change("../outside.yaml", "x: 1", "bad")
