"""
ChatGPT / Codex Usage & Rate Limit Client.
Directly interfaces with ~/.codex/auth.json and ChatGPT backend wham/usage endpoint.
Automatically parses 5H rolling limit, weekly quota, plan details, and reset timers.
Uses compact time units (d, h, m, 5H).
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import requests


def format_duration_compact(seconds: int) -> str:
    """Format duration in seconds into compact string (e.g. 1d18h, 3h7m, 45m)."""
    if seconds <= 0:
        return "即将重置"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{minutes}m" if minutes > 0 else "<1m")
    
    return "".join(parts)


def format_window_name_compact(window_seconds: int) -> str:
    """Translate window duration to display title."""
    if window_seconds <= 18000:  # <= 5 hours
        return "5H"
    elif window_seconds <= 86400:  # <= 24 hours
        return "24H"
    elif window_seconds <= 604800:  # <= 7 days
        return "周限额"
    else:
        return f"{window_seconds // 86400}d"


class CodexUsageClient:
    """Client for fetching ChatGPT Plus / Codex usage stats."""
    
    def __init__(self, auth_file_path: Optional[str] = None):
        if auth_file_path:
            self.auth_path = os.path.expanduser(auth_file_path)
        else:
            self.auth_path = os.path.expanduser("~/.codex/auth.json")
        
        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: float = 0
        self.last_error: Optional[str] = None
        self._auth_mtime: float = 0
        self._access_token: Optional[str] = None
        self._account_id: Optional[str] = None

    def reload_auth_if_needed(self) -> bool:
        """Check if auth.json was modified and reload tokens.
        If auth.json is missing tokens (e.g. CC Switch swapped to third-party proxy),
        fall back to CC Switch SQLite database (~/.cc-switch/cc-switch.db).
        """
        token_found = False
        
        # 1. First try reading auth.json
        if os.path.exists(self.auth_path):
            try:
                mtime = os.path.getmtime(self.auth_path)
                if mtime != self._auth_mtime or not self._access_token:
                    with open(self.auth_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    tokens = data.get("tokens", {})
                    token = tokens.get("access_token")
                    acct_id = tokens.get("account_id")
                    if token:
                        self._access_token = token
                        self._account_id = acct_id
                        self._auth_mtime = mtime
                        self.last_error = None
                        token_found = True
            except Exception:
                pass
        
        if token_found:
            return True
            
        # 2. If token not in auth.json, fallback to CC Switch database
        fb = self._get_fallback_tokens_from_cc_switch()
        if fb:
            self._access_token, self._account_id = fb
            self.last_error = None
            return True
            
        if not self._access_token:
            self.last_error = "未找到有效的 ChatGPT OAuth 凭证 (auth.json 与 CC Switch 均无可用 Token)"
            return False
            
        return True

    def _get_fallback_tokens_from_cc_switch(self) -> Optional[tuple]:
        """Attempt to read official OpenAI OAuth tokens from CC Switch local database."""
        db_path = os.path.expanduser("~/.cc-switch/cc-switch.db")
        if not os.path.exists(db_path):
            return None
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT settings_config FROM providers WHERE app_type='codex' AND (name LIKE '%Official%' OR name LIKE '%OpenAI%')"
            )
            rows = cursor.fetchall()
            conn.close()
            for (settings_raw,) in rows:
                if not settings_raw:
                    continue
                try:
                    settings = json.loads(settings_raw)
                    auth = settings.get("auth", {})
                    tokens = auth.get("tokens", {})
                    token = tokens.get("access_token")
                    acct_id = tokens.get("account_id")
                    if token:
                        return token, acct_id
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def fetch_usage(self, force: bool = False, timeout: int = 8) -> Dict[str, Any]:
        """
        Fetch ChatGPT / Codex usage stats from backend-api/wham/usage.
        Returns parsed structured dictionary.
        """
        now = time.time()
        if not force and self.cached_data and (now - self.last_fetch_time < 10):
            return self.cached_data
        
        if not self.reload_auth_if_needed():
            return {
                "success": False,
                "error": self.last_error or "未认证",
                "plan_type": "未知",
                "primary_window": None,
                "secondary_window": None,
                "five_hour_window": None,
                "weekly_window": None,
                "reset_credits": 0,
            }
        
        url = "https://chatgpt.com/backend-api/wham/usage"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        if self._account_id:
            headers["ChatGPT-Account-Id"] = self._account_id

        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                raw = resp.json()
                self.last_error = None
                parsed = self._parse_response(raw)
                self.cached_data = parsed
                self.last_fetch_time = now
                return parsed
            elif resp.status_code == 401:
                self.last_error = "登录凭证失效 (401)"
                return {"success": False, "error": self.last_error, "plan_type": "未登录"}
            elif resp.status_code == 429:
                self.last_error = "请求频繁 (429)"
                if self.cached_data:
                    return self.cached_data
                return {"success": False, "error": self.last_error, "plan_type": "限频"}
            else:
                self.last_error = f"API 错误 ({resp.status_code})"
                if self.cached_data:
                    return self.cached_data
                return {"success": False, "error": self.last_error, "plan_type": "错误"}
        except requests.exceptions.Timeout:
            self.last_error = "网络超时"
            if self.cached_data:
                return self.cached_data
            return {"success": False, "error": self.last_error, "plan_type": "超时"}
        except Exception as e:
            self.last_error = f"请求失败: {e}"
            if self.cached_data:
                return self.cached_data
            return {"success": False, "error": self.last_error, "plan_type": "异常"}

    def _parse_window(self, win: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Helper to parse a rate limit window object."""
        if not win or not isinstance(win, dict):
            return None
            
        used_pct = int(win.get("used_percent", 0))
        remain_pct = max(0, 100 - used_pct)
        win_secs = int(win.get("limit_window_seconds", 604800))
        reset_after = int(win.get("reset_after_seconds", 0))
        reset_at = win.get("reset_at")
        
        reset_at_str = ""
        if reset_at:
            try:
                dt = datetime.fromtimestamp(reset_at)
                reset_at_str = dt.strftime("%m-%d %H:%M")
            except Exception:
                pass
        
        if remain_pct > 30:
            bar_color = "#3B82F6"
        elif remain_pct > 10:
            bar_color = "#F59E0B"
        else:
            bar_color = "#EF4444"
            
        return {
            "name": format_window_name_compact(win_secs),
            "used_percent": used_pct,
            "remaining_percent": remain_pct,
            "window_seconds": win_secs,
            "reset_after_seconds": reset_after,
            "reset_countdown": format_duration_compact(reset_after),
            "reset_at_str": reset_at_str,
            "bar_color": bar_color,
            "reset_at": reset_at,
        }

    def _parse_response(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw JSON response from wham/usage into structured models."""
        plan_type = raw.get("plan_type", "plus").upper()
        rate_limit = raw.get("rate_limit", {}) or {}
        
        pw_info = self._parse_window(rate_limit.get("primary_window"))
        sw_info = self._parse_window(rate_limit.get("secondary_window"))
        
        five_hour_info = None
        weekly_info = None
        
        all_windows = [w for w in [pw_info, sw_info] if w]
        
        add_limits = raw.get("additional_rate_limits")
        if isinstance(add_limits, list):
            for al in add_limits:
                parsed_al = self._parse_window(al)
                if parsed_al:
                    all_windows.append(parsed_al)
                    
        for w in all_windows:
            w_sec = w.get("window_seconds", 0)
            if w_sec <= 18000 and not five_hour_info:
                five_hour_info = w
            elif w_sec > 86400 and not weekly_info:
                weekly_info = w
            elif not weekly_info:
                weekly_info = w
                
        if not weekly_info and pw_info:
            weekly_info = pw_info

        reset_credits_obj = raw.get("rate_limit_reset_credits", {}) or {}
        reset_credits_count = reset_credits_obj.get("available_count", 0)

        credits_obj = raw.get("credits", {}) or {}
        has_credits = credits_obj.get("has_credits", False)
        balance = credits_obj.get("balance", "0")

        return {
            "success": True,
            "email": raw.get("email", ""),
            "plan_type": plan_type,
            "allowed": rate_limit.get("allowed", True),
            "limit_reached": rate_limit.get("limit_reached", False),
            "primary_window": pw_info,
            "secondary_window": sw_info,
            "five_hour_window": five_hour_info,
            "weekly_window": weekly_info,
            "reset_credits": reset_credits_count,
            "has_credits": has_credits,
            "balance": balance,
            "fetch_time": datetime.now().strftime("%H:%M:%S"),
        }


if __name__ == "__main__":
    client = CodexUsageClient()
    res = client.fetch_usage()
    print("Fetch Result:", json.dumps(res, indent=2, ensure_ascii=False))
