"""Read Claude subscription limits using the user's local Claude Code login."""

import json
import hashlib
from pathlib import Path
import math
import os
import time
import tempfile
from email.utils import parsedate_to_datetime
from datetime import datetime

import requests

from core.quota_tracker import format_duration_compact


class ClaudeUsageClient:
    def __init__(self, auth_file_path=None, state_path=None):
        self.auth_path = os.path.expanduser(auth_file_path or "~/.claude/.credentials.json")
        self.auto_auth = os.path.normcase(os.path.abspath(self.auth_path)) == os.path.normcase(os.path.abspath(os.path.expanduser("~/.claude/.credentials.json")))
        self.session = requests.Session()
        self.cached_data = None
        self.next_fetch = 0.0
        self.state_path = state_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "claude_usage_state.json")
        self.last_good = None
        self.failures = 0
        self.account_key = None
        self.credential_key = None
        try:
            self._read_auth()
        except (OSError, ValueError, TypeError):
            pass
        self._load_state()


    @staticmethod
    def _window(raw, seconds, name):
        if not isinstance(raw, dict) or raw.get("utilization") is None:
            return None
        used = float(raw["utilization"])
        if not math.isfinite(used):
            raise ValueError("Invalid utilization")
        used = min(100.0, max(0.0, used))
        reset_text = raw.get("resets_at")
        if not isinstance(reset_text, str):
            raise ValueError("Missing reset time")
        reset_date = datetime.fromisoformat(reset_text.replace("Z", "+00:00"))
        if reset_date.tzinfo is None:
            raise ValueError("Reset time requires a timezone")
        reset = reset_date.timestamp()
        remaining = round(100 - used, 1)
        return {
            "name": name,
            "used_percent": round(used),
            "remaining_percent": remaining,
            "window_seconds": seconds,
            "reset_at": int(reset),
            "reset_after_seconds": max(0, int(reset - time.time())),
            "reset_countdown": format_duration_compact(max(0, int(reset - time.time()))),
            "bar_color": "#10B981" if remaining > 50 else "#F59E0B" if remaining >= 20 else "#EF4444",
        }

    def _read_auth(self):
        paths = [Path(self.auth_path)]
        if self.auto_auth:
            # CC Switch keeps Claude Code subscriptions separate from Claude Desktop.
            managed = list((Path.home() / ".cc-switch" / "claude-accounts").glob("*/config/.credentials.json"))
            if managed:
                paths = managed
        candidates = []
        for path in paths:
            try:
                auth = json.loads(path.read_text(encoding="utf-8")).get("claudeAiOauth", {})
                if auth.get("accessToken"):
                    candidates.append((float(auth.get("expiresAt", 0)), str(path), auth))
            except (OSError, ValueError, TypeError):
                continue
        if not candidates and self.auto_auth and paths != [Path(self.auth_path)]:
            try:
                auth = json.loads(Path(self.auth_path).read_text(encoding="utf-8")).get("claudeAiOauth", {})
                if auth.get("accessToken"):
                    candidates.append((float(auth.get("expiresAt", 0)), self.auth_path, auth))
            except (OSError, ValueError, TypeError):
                pass
        if not candidates:
            raise FileNotFoundError("Claude Code credentials unavailable")
        # Follow the most recently renewed subscription when several logins remain.
        _, source, auth = max(candidates, key=lambda candidate: candidate[0])
        identity = auth.get("accountUuid", "") + ":" + auth.get("organizationUuid", "")
        account = hashlib.sha256((identity if identity != ":" else auth["accessToken"]).encode()).hexdigest()
        credential = hashlib.sha256((source + auth["accessToken"]).encode()).hexdigest()
        if self.credential_key and credential != self.credential_key:
            self.cached_data = None
            self.next_fetch = 0
            self.failures = 0
            if account != self.account_key:
                self.last_good = None
        self.account_key, self.credential_key = account, credential
        return auth

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as stream:
                state = json.load(stream)
            if state.get("account_key") != self.account_key or not self.account_key:
                return
            self.last_good = state.get("last_good")
            if state.get("credential_key") != self.credential_key:
                return
            self.failures = max(0, int(state.get("failures", 0)))
            wait = max(0, min(3600, float(state.get("retry_at", 0)) - time.time()))
            self.next_fetch = time.monotonic() + wait
            if wait:
                self.cached_data = state.get("cached_data") or self._failure("Claude 请求受限，等待自动重试", state.get("retry_at", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _save_state(self, retry_at):
        temporary = None
        try:
            directory = os.path.dirname(os.path.abspath(self.state_path))
            os.makedirs(directory, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as stream:
                temporary = stream.name
                json.dump({"account_key": self.account_key, "credential_key": self.credential_key, "last_good": self.last_good, "failures": self.failures, "retry_at": retry_at, "cached_data": self.cached_data}, stream, ensure_ascii=False)
            os.replace(temporary, self.state_path)
        except OSError:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _retry_after(value):
        try:
            return max(0, float(value))
        except (ValueError, TypeError):
            try:
                return max(0, parsedate_to_datetime(value).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                return 0

    def _failure(self, error, retry_at):
        result = dict(self.last_good or {})
        result.update(success=bool(self.last_good), stale=bool(self.last_good), error=error, retry_at=retry_at)
        return result

    @staticmethod
    def _refresh_countdowns(result):
        result = dict(result)
        for field in ("five_hour_window", "weekly_window"):
            if result.get(field):
                window = dict(result[field])
                remaining = max(0, int(window["reset_at"] - time.time()))
                window.update(reset_after_seconds=remaining, reset_countdown=format_duration_compact(remaining))
                result[field] = window
        return result

    def fetch_usage(self, force=False):
        retry_seconds = 300
        result = None
        try:
            auth = self._read_auth()
            # Re-read login first, so switching/renewing an account clears old backoff.
            if time.monotonic() < self.next_fetch and self.cached_data is not None:
                return self._refresh_countdowns(self.cached_data)
            token = auth.get("accessToken")
            if not token:
                result = {"success": False, "error": "请先在 Claude Code 中登录订阅账户"}
            else:
                with self.session.get(
                    "https://api.anthropic.com/api/oauth/usage",
                    headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20",
                             "User-Agent": "desktop-floating-widget/1.0"}, timeout=(3, 5),
                ) as response:
                    if response.status_code in (401, 403):
                        result = {"success": False, "error": "Claude 登录已失效，请在 Claude Code 中重新登录"}
                    elif response.status_code == 429:
                        self.failures = min(5, self.failures + 1)
                        retry_seconds = max(min(3600, 300 * 2 ** (self.failures - 1)),
                                            min(3600, self._retry_after(response.headers.get("Retry-After"))))
                        result = self._failure("Claude 请求受限，等待自动重试", time.time() + retry_seconds)
                    else:
                        response.raise_for_status()
                        raw = response.json()
                        five_hour = self._window(raw.get("five_hour"), 18000, "5H")
                        weekly = self._window(raw.get("seven_day"), 604800, "周限额")
                        if five_hour or weekly:
                            self.failures = 0
                            retry_seconds = 300
                            result = {"success": True, "plan_type": str(auth.get("subscriptionType") or "Claude").upper(),
                                      "five_hour_window": five_hour, "weekly_window": weekly,
                                      "fetch_time": datetime.now().strftime("%H:%M:%S"), "fetched_at": time.time(),
                                      "account_key": self.account_key}
                            self.last_good = dict(result)
                        else:
                            result = self._failure("当前账户未返回订阅额度", time.time() + retry_seconds)
        except FileNotFoundError:
            result = {"success": False, "error": "请先在 Claude Code 中登录订阅账户"}
        except requests.RequestException:
            result = self._failure("Claude 额度连接失败，等待自动重试", time.time() + retry_seconds)
        except (ValueError, TypeError, KeyError, OSError):
            result = self._failure("无法读取 Claude 登录或额度数据", time.time() + retry_seconds)
        self.cached_data = result
        self.next_fetch = time.monotonic() + retry_seconds
        self._save_state(time.time() + retry_seconds)
        return self._refresh_countdowns(result)
