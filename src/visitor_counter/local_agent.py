from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_ALLOWED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".sh", ".ps1", ".kt", ".kts", ".xml", ".service"}
_EXCLUDED = {".git", ".venv", "venv", "models", "data", "logs", "build", "dist", "__pycache__"}
_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|token|api[_-]?key|secret)\s*[:=]\s*[^\s#]+"),
    re.compile(r"(?i)(rtsp|https?)://[^\s/:]+:[^\s@]+@"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


@dataclass(frozen=True)
class KnowledgeChunk:
    path: str
    text: str
    score: int


@dataclass(frozen=True)
class ChangeProposal:
    path: str
    expected_sha256: str
    new_content: str
    reason: str


def redact_secrets(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


class ProjectKnowledgeBase:
    """Simple local retrieval over repository text files; no project data leaves the Pi."""

    def __init__(self, root: Path, max_file_bytes: int = 256_000) -> None:
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes
        self.files = self._discover()

    def _discover(self) -> list[Path]:
        result: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _ALLOWED_SUFFIXES:
                continue
            if any(part in _EXCLUDED for part in path.relative_to(self.root).parts):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue
            result.append(path)
        return sorted(result)

    def search(self, query: str, limit: int = 8, per_file_chars: int = 5000) -> list[KnowledgeChunk]:
        terms = {x.lower() for x in re.findall(r"[A-Za-zÄÖÜäöüß0-9_\-]{3,}", query)}
        ranked: list[KnowledgeChunk] = []
        for path in self.files:
            try:
                text = redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            low = text.lower()
            score = sum(low.count(term) for term in terms)
            rel = str(path.relative_to(self.root))
            if terms and score == 0 and not any(term in rel.lower() for term in terms):
                continue
            ranked.append(KnowledgeChunk(rel, text[:per_file_chars], score))
        ranked.sort(key=lambda x: (-x.score, x.path))
        return ranked[:limit]


class LocalGemmaAgent:
    """Chat/RAG client for a localhost llama.cpp server running Gemma 4.

    The agent can inspect the project and propose small edits. It never applies
    changes from model output automatically; apply_proposal performs path,
    hash, secret and size checks and must be invoked by an explicit UI action.
    """

    def __init__(self, root: Path, endpoint: str = "http://127.0.0.1:8080/v1/chat/completions", model: str = "gemma-4-e2b-it") -> None:
        self.root = root.resolve()
        self.endpoint = self._validated_loopback_endpoint(endpoint)
        self.model = model
        self.kb = ProjectKnowledgeBase(self.root)

    @staticmethod
    def _validated_loopback_endpoint(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Der lokale Assistent darf nur einen HTTP-Loopback-Endpunkt verwenden")
        if parsed.username or parsed.password:
            raise ValueError("Zugangsdaten in der lokalen Agent-URL sind nicht erlaubt")
        return endpoint

    def ask(self, message: str, history: Iterable[dict[str, str]] = ()) -> str:
        chunks = self.kb.search(message)
        context = "\n\n".join(f"### {c.path}\n{c.text}" for c in chunks)
        system = (
            "Du bist der lokale Projektassistent eines datenschutzorientierten Personenzaehlers. "
            "Arbeite nur mit dem bereitgestellten Projektkontext. Erfinde keine Messwerte. "
            "Keine Personenidentifikation, keine Gesichtserkennung und keine Umgehung von Datenschutzsperren. "
            "Wenn du Codeaenderungen empfiehlst, beschreibe sie klein, reversibel und testbar. "
            "Du darfst niemals behaupten, eine Aenderung bereits angewendet zu haben."
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(list(history)[-8:])
        messages.append({"role": "user", "content": f"Projektkontext:\n{context}\n\nFrage:\n{message}"})
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 1200}).encode()
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=90) as response:  # nosec B310 - endpoint is validated as loopback HTTP above
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError) as exc:
            raise RuntimeError(f"Lokaler Gemma-Dienst nicht erreichbar: {exc}") from exc
        return str(data["choices"][0]["message"]["content"])

    def propose_file_change(self, path: str, new_content: str, reason: str) -> ChangeProposal:
        target = self._safe_target(path)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        if len(new_content.encode("utf-8")) > 512_000:
            raise ValueError("Aenderung ist fuer den lokalen Assistenten zu gross")
        if redact_secrets(new_content) != new_content:
            raise ValueError("Aenderung enthaelt moegliche Zugangsdaten oder Secrets")
        return ChangeProposal(path, sha256(old.encode()).hexdigest(), new_content, reason)

    def apply_proposal(self, proposal: ChangeProposal, *, confirmed: bool = False) -> None:
        if not confirmed:
            raise PermissionError("Explizite Benutzerbestaetigung erforderlich")
        target = self._safe_target(proposal.path)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        if sha256(old.encode()).hexdigest() != proposal.expected_sha256:
            raise RuntimeError("Datei wurde seit dem Vorschlag veraendert")
        if redact_secrets(proposal.new_content) != proposal.new_content:
            raise ValueError("Aenderung enthaelt moegliche Secrets")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposal.new_content, encoding="utf-8")

    def _safe_target(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError("Pfad liegt ausserhalb des Projekts")
        rel_parts = target.relative_to(self.root).parts
        if any(part in _EXCLUDED for part in rel_parts):
            raise ValueError("Dieser Projektbereich darf nicht veraendert werden")
        if target.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise ValueError("Dateityp ist fuer Assistentenaenderungen nicht freigegeben")
        return target


def recommended_llama_server_command(model_path: str) -> list[str]:
    """Conservative Raspberry Pi default; E4B can be selected on 16 GB systems."""
    return [
        os.environ.get("LLAMA_SERVER", "llama-server"),
        "-m", model_path,
        "--host", "127.0.0.1",
        "--port", "8080",
        "-c", "8192",
        "-t", "4",
    ]
