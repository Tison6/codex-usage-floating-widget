"""Read Claude Code session state without scanning conversation history."""

import json
import os
from pathlib import Path
import re
import time

import psutil


class ClaudeActivityTracker:
    def __init__(self, roots=None):
        self._explicit_roots = roots
        self._roots = []
        self._next_discovery = 0

    def _session_roots(self):
        if self._explicit_roots is not None:
            return [Path(root) for root in self._explicit_roots]
        if time.monotonic() >= self._next_discovery:
            roots = [Path.home() / ".claude"]
            configured = os.environ.get("CLAUDE_CONFIG_DIR")
            if configured:
                roots.append(Path(configured))
            try:
                roots.extend((Path.home() / ".cc-switch" / "claude-accounts").glob("*/config"))
            except OSError:
                pass
            self._roots = list(dict.fromkeys(roots))
            self._next_discovery = time.monotonic() + 30
        return self._roots

    @staticmethod
    def _legacy_session_active(root, session):
        """Older CLI sessions have no status field. Inspect only their own log tail."""
        session_id = str(session.get("sessionId", ""))
        if not re.fullmatch(r"[A-Za-z0-9-]+", session_id):
            return False
        project = re.sub(r"[^A-Za-z0-9]", "-", str(session.get("cwd", "")))
        path = root / "projects" / project / (session_id + ".jsonl")
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > 90:
                return False
            with path.open("rb") as stream:
                stream.seek(max(0, stat.st_size - 65536))
                lines = stream.read().splitlines()
            for line in reversed(lines):
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if item.get("isSidechain"):
                    continue
                message = item.get("message") or {}
                if item.get("type") == "assistant":
                    return message.get("stop_reason") not in ("end_turn", "stop_sequence")
                if item.get("type") == "user":
                    content = message.get("content", "")
                    if isinstance(content, str) and "[Request interrupted by user" in content:
                        return False
                    return True
        except (OSError, ValueError, TypeError):
            pass
        return False

    def check_is_running(self):
        for root in self._session_roots():
            try:
                sessions = list((root / "sessions").glob("*.json"))
            except OSError:
                continue
            for path in sessions:
                try:
                    session = json.loads(path.read_text(encoding="utf-8"))
                    if session.get("kind", "interactive") != "interactive":
                        continue
                    process = psutil.Process(int(session["pid"]))
                    recorded_at = max(session.get("startedAt", 0), session.get("updatedAt", 0)) / 1000
                    if recorded_at and process.create_time() > recorded_at + 5:
                        continue
                    status = session.get("status")
                    if status in ("working", "running", "busy", "thinking", "responding", "processing", "tool_use"):
                        return True, "session_" + status
                    if status is None and self._legacy_session_active(root, session):
                        return True, "session_log_active"
                except (OSError, ValueError, TypeError, KeyError, psutil.Error):
                    continue
        return False, "all_idle"
