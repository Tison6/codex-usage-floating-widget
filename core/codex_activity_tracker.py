"""
Mature Real-Time Activity Monitor for OpenAI Codex / ChatGPT Codex.
Tracks active generation and tool execution by reading native session rollout event logs
and process trees rather than volatile CPU sampling, eliminating status jitter ("反复横跳").
"""

import os
import glob
import json
import time
from typing import Optional, Tuple
import psutil


class CodexActivityTracker:
    """Accurate state monitor for Codex desktop/CLI."""

    def __init__(self, codex_home: Optional[str] = None):
        self.codex_home = codex_home or os.path.expanduser("~/.codex")
        self.sessions_dir = os.path.join(self.codex_home, "sessions")
        self._cached_rollout_file: Optional[str] = None
        self._last_scan_time: float = 0
        self._is_running_state: bool = False
        self._last_active_timestamp: float = 0

    def get_latest_rollout_file(self) -> Optional[str]:
        """Find the active/latest session rollout jsonl file."""
        now = time.time()
        if self._cached_rollout_file and (now - self._last_scan_time < 2.5):
            return self._cached_rollout_file

        self._last_scan_time = now
        
        if not os.path.exists(self.sessions_dir):
            return None

        # Fast search: check today's folder first
        today_files = glob.glob(f"{self.sessions_dir}/*/*/*/*.jsonl")
        if today_files:
            today_files.sort(key=os.path.getmtime, reverse=True)
            self._cached_rollout_file = today_files[0]
            return self._cached_rollout_file

        # Fallback search
        all_files = glob.glob(f"{self.sessions_dir}/**/*.jsonl", recursive=True)
        if all_files:
            all_files.sort(key=os.path.getmtime, reverse=True)
            self._cached_rollout_file = all_files[0]
            return self._cached_rollout_file

        return None

    def check_is_running(self) -> Tuple[bool, str]:
        """
        Determine if Codex is actively reasoning, calling tools, or generating output.
        Returns (is_running, reason).
        """
        rollout = self.get_latest_rollout_file()
        now = time.time()

        if not rollout or not os.path.exists(rollout):
            return False, "no_session"

        try:
            mtime = os.path.getmtime(rollout)
            age = now - mtime

            # If rollout has not been modified in > 8s, treat as idle
            if age > 8.0:
                return False, "idle_timeout"

            # Read the tail 3KB to extract the latest event
            with open(rollout, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                seek_pos = max(0, size - 3072)
                f.seek(seek_pos)
                tail_bytes = f.read()

            lines = [l.strip() for l in tail_bytes.decode("utf-8", errors="ignore").split("\n") if l.strip()]
            
            last_payload_type = None
            for line in reversed(lines):
                try:
                    obj = json.loads(line)
                    payload = obj.get("payload", {})
                    if isinstance(payload, dict):
                        last_payload_type = payload.get("type")
                        if last_payload_type:
                            break
                except Exception:
                    continue

            # If turn explicitly finished -> Idle
            if last_payload_type in ("task_complete", "task_failed", "turn_complete"):
                return False, f"complete_{last_payload_type}"

            # If an active event occurred recently (within 4.5s) -> Running
            if age < 4.5:
                self._last_active_timestamp = now
                return True, f"active_{last_payload_type}"

            # If tool execution or reasoning is ongoing within 7s -> Running
            if last_payload_type in ("custom_tool_call", "reasoning", "task_started") and age < 7.0:
                return True, f"in_progress_{last_payload_type}"

            return False, "idle"

        except Exception as e:
            return False, f"error_{e}"
