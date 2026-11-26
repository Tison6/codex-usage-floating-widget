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
from datetime import datetime, timedelta
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

        # 2. Recent session directories. A live rollout can only be in the
        # current or previous day directory because stale files are rejected
        # after 90 seconds by check_file_running(). Avoid walking every date
        # below the sessions root on each activity poll.
        if os.path.exists(self.sessions_dir):
            try:
                recent_files: List[str] = []
                now = datetime.now()
                for day_offset in (0, 1):
                    day = now - timedelta(days=day_offset)
                    day_dir = os.path.join(
                        self.sessions_dir,
                        day.strftime("%Y"),
                        day.strftime("%m"),
                        day.strftime("%d"),
                    )
                    recent_files.extend(glob.glob(os.path.join(day_dir, "*.jsonl")))

                def safe_mtime(path: str) -> float:
                    try:
                        return os.path.getmtime(path)
                    except OSError:
                        return 0.0

                recent_files.sort(key=safe_mtime, reverse=True)
                for path in recent_files[:3]:
                    if path not in candidates and os.path.exists(path):
                        candidates.append(path)
            except Exception:
                pass

        self._cached_candidates = candidates
        # Keep the file-result cache proportional to the active candidates.
        self._file_cache = {
            path: self._file_cache[path]
            for path in candidates
            if path in self._file_cache
        }
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
            if cached[3].startswith("active_") and age >= 8.0:
                return False, "idle_no_recent_events"
            return cached[2], cached[3]

        # After the first observation, inspect new data plus a small overlap.
        read_size = min(size, 4 * 1024 * 1024)
        if cached and size >= cached[1]:
            read_size = min(read_size, max(65536, size - cached[1] + 65536))
        try:
            with open(path, "rb") as f:
                f.seek(size - read_size)
                data = f.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return False, f"read_error_{e}"

        lines = [l.strip() for l in data.split("\n") if l.strip()]
        
        last_active_event = None
        event_markers = (
            '"task_complete"', '"task_failed"', '"turn_aborted"', '"turn_complete"',
            '"task_started"', '"custom_tool_call"', '"reasoning"',
            '"custom_tool_call_output"', '"item_started"',
        )
        for l in reversed(lines):
            if not any(marker in l for marker in event_markers):
                continue
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

        if cached and size >= cached[1] and cached[3] == "task_started_active":
            self._file_cache[path] = (mtime, size, True, "task_started_active")
            return True, "task_started_active"

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
