"""
Mature Real-Time Activity Monitor for OpenAI Codex / ChatGPT Codex.
Tracks active turn lifecycle (task_started -> task_complete / turn_aborted)
across user threads from state_5.sqlite and session logs, eliminating status jitter ("反复横跳").
"""

import os
import glob
import json
import time
import sqlite3
from typing import Optional, Tuple, List, Dict, Any


class CodexActivityTracker:
    """
    Accurate, jitter-free state monitor for Codex desktop/CLI/VSCode.
    Uses native turn lifecycle state matching with mtime-delta caching.
    """

    def __init__(self, codex_home: Optional[str] = None):
        self.codex_home = codex_home or os.path.expanduser("~/.codex")
        self.sessions_dir = os.path.join(self.codex_home, "sessions")
        self.db_path = os.path.join(self.codex_home, "state_5.sqlite")
        
        self._cached_candidates: List[str] = []
        self._last_candidate_scan: float = 0
        self._file_cache: Dict[str, Tuple[float, int, bool, str]] = {}
        self._last_active_timestamp: float = 0

    def get_candidate_rollouts(self) -> List[str]:
        """
        Collect active candidate rollout paths from state_5.sqlite and session directories.
        Results are cached for 2.0s to minimize disk I/O.
        """
        now = time.time()
        if self._cached_candidates and (now - self._last_candidate_scan < 2.0):
            return self._cached_candidates

        self._last_candidate_scan = now
        candidates: List[str] = []

        # 1. State DB: latest user interactive threads (exclude subagents and maintenance)
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1.0)
                cur = conn.cursor()
                cur.execute("""
                    SELECT rollout_path FROM threads 
                    WHERE source NOT LIKE '%subagent%'
                    ORDER BY updated_at DESC LIMIT 3
                """)
                for (rpath,) in cur.fetchall():
                    if rpath:
                        clean = rpath.replace(r"\\?\ ", "").replace(r"\\?\/", "").replace(r"\\?\\", "")
                        clean = os.path.expanduser(clean)
                        if os.path.exists(clean) and clean not in candidates:
                            candidates.append(clean)
                conn.close()
            except Exception:
                pass

        # 2. Today's sessions directory (handles new sessions not yet committed to DB or CLI runs)
        if os.path.exists(self.sessions_dir):
            today_files = glob.glob(f"{self.sessions_dir}/*/*/*/*.jsonl")
            if today_files:
                today_files.sort(key=os.path.getmtime, reverse=True)
                for f in today_files[:3]:
                    if f not in candidates:
                        candidates.append(f)

        self._cached_candidates = candidates
        return candidates

    def check_file_running(self, path: str) -> Tuple[bool, str]:
        """
        Inspect turn lifecycle of a specific rollout file.
        Scans backward from the tail:
        - If first lifecycle event is task_complete / task_failed / turn_aborted -> Idle (False).
        - If first lifecycle event is task_started without completion within 90s -> Running (True).
        """
        now = time.time()
        try:
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
        except OSError:
            return False, "os_error"

        age = now - mtime
        if age > 90.0:
            return False, f"idle_timeout_{age:.0f}s"

        # Check memory cache: if mtime and size did not change, return previous evaluation
        cached = self._file_cache.get(path)
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2], cached[3]

        # Read up to 4MB from tail
        read_size = min(size, 4 * 1024 * 1024)
        try:
            with open(path, "rb") as f:
                f.seek(size - read_size)
                data = f.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return False, f"read_error_{e}"

        lines = [l.strip() for l in data.split("\n") if l.strip()]
        
        last_active_event = None
        for l in reversed(lines):
            try:
                o = json.loads(l)
                p = o.get("payload", {})
                pt = p.get("type") if isinstance(p, dict) else ""
                
                # Terminal lifecycle events mean turn finished
                if pt in ("task_complete", "task_failed", "turn_aborted", "turn_complete"):
                    res = (False, f"completed_{pt}")
                    self._file_cache[path] = (mtime, size, res[0], res[1])
                    return res
                    
                # task_started without subsequent terminal event means active turn
                if pt == "task_started":
                    res = (True, "task_started_active")
                    self._file_cache[path] = (mtime, size, res[0], res[1])
                    return res
                    
                if not last_active_event and pt in ("custom_tool_call", "reasoning", "custom_tool_call_output", "item_started"):
                    last_active_event = pt
            except Exception:
                continue

        # Fallback for sub-agent or streaming writes without explicit task_started
        if last_active_event and age < 8.0:
            res = (True, f"active_{last_active_event}")
            self._file_cache[path] = (mtime, size, res[0], res[1])
            return res

        res = (False, "idle_no_active_turn")
        self._file_cache[path] = (mtime, size, res[0], res[1])
        return res

    def check_is_running(self) -> Tuple[bool, str]:
        """
        Determine if Codex is actively running.
        Returns (is_running, reason).
        """
        candidates = self.get_candidate_rollouts()
        if not candidates:
            return False, "no_candidates"

        for f in candidates:
            is_run, reason = self.check_file_running(f)
            if is_run:
                self._last_active_timestamp = time.time()
                return True, f"{os.path.basename(f)}:{reason}"

        return False, "all_idle"
