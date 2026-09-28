"""
AIHub Relay Client (https://aihub.top).
Handles session login, balance tracking, rate multiplier <= 0.2 filtering,
and caching of the latest 5 Pelican (鹈鹕) verification test images.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests


def format_iso_timestamp(iso_str: Optional[str]) -> str:
    """Format ISO 8601 string to friendly local datetime (MM-DD HH:MM:SS)."""
    if not iso_str:
        return "--:--:--"
    try:
        # e.g. 2026-09-28T16:13:48.901269+08:00
        clean_str = iso_str.split(".")[0]
        if "+" in iso_str:
            tz_part = iso_str.split("+")[1]
            dt = datetime.fromisoformat(iso_str)
        elif "Z" in iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%m-%d %H:%M:%S")
    except Exception:
        # Fallback to string slicing
        try:
            return iso_str[5:19].replace("T", " ")
        except Exception:
            return iso_str


class AIHubClient:
    """Client for querying AIHub accounts, low-multiplier groups, and pelican test images."""

    LOGIN_URL = "https://aihub.top/api/v1/auth/login"
    USER_ME_URL = "https://aihub.top/api/v1/auth/me"
    PROVIDERS_URL = "https://aihub.top/api/v1/public/providers"
    USAGE_STATS_URL = "https://aihub.top/api/v1/public/groups/usage-stats"

    def __init__(self, email: str = "", password: str = "", cache_dir: Optional[str] = None):
        self.email = email
        self.password = password
        
        # Load from config.json if not passed directly
        if not self.email or not self.password:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cfg_path = os.path.join(base_dir, "config.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                    self.email = self.email or cfg_data.get("aihub_email", "")
                    self.password = self.password or cfg_data.get("aihub_password", "")
                except Exception:
                    pass

        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        
        # Cache directory for pelican images
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.cache_dir = os.path.join(base_dir, "data", "pelican_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        self.cached_balance: Optional[float] = None
        self.cached_providers: Optional[List[Dict[str, Any]]] = None
        self.cached_pelicans: List[Dict[str, Any]] = []
        self.last_fetch_time: float = 0
        self.last_error: Optional[str] = None

    def ensure_authenticated(self, timeout: int = 8) -> bool:
        """Ensure valid JWT access token from login or cached session."""
        now = time.time()
        if self.access_token and now < self.token_expiry:
            return True

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        payload = {"email": self.email, "password": self.password}

        try:
            resp = requests.post(self.LOGIN_URL, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                d_inner = data.get("data", {})
                self.access_token = d_inner.get("access_token")
                # Tokens usually valid for 24h, expire after 12h
                self.token_expiry = now + 43200
                user = d_inner.get("user", {})
                if user and "balance" in user:
                    self.cached_balance = float(user["balance"])
                self.last_error = None
                return True
            else:
                self.last_error = f"登录失败 (HTTP {resp.status_code})"
                return False
        except Exception as e:
            self.last_error = f"登录网络异常: {e}"
            return False

    def fetch_user_balance(self, timeout: int = 8) -> Optional[float]:
        """Fetch current account balance in CNY."""
        if not self.ensure_authenticated(timeout=timeout):
            return self.cached_balance

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            resp = requests.get(self.USER_ME_URL, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                bal = data.get("balance")
                if bal is not None:
                    self.cached_balance = float(bal)
                    return self.cached_balance
            elif resp.status_code == 401:
                # Force re-login next time
                self.access_token = None
        except Exception:
            pass
        return self.cached_balance

    def fetch_data(self, force: bool = False, timeout: int = 8) -> Dict[str, Any]:
        """
        Fetch AIHub status, user balance, top 3 accounts (multiplier <= 0.2),
        and latest 5 Pelican test images with local caching.
        """
        now = time.time()
        if not force and self.cached_providers and (now - self.last_fetch_time < 60):
            return {
                "success": True,
                "balance": self.cached_balance,
                "top_groups": self.cached_providers,
                "pelican_images": self.cached_pelicans,
                "updated_at": time.strftime("%H:%M:%S", time.localtime(self.last_fetch_time)),
            }

        # 1. Update user balance
        balance = self.fetch_user_balance(timeout=timeout)

        # 2. Fetch public providers & usage stats
        headers = {"User-Agent": "Mozilla/5.0"}
        providers_raw = []
        try:
            resp = requests.get(self.PROVIDERS_URL, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                providers_raw = resp.json().get("data", {}).get("items", [])
        except Exception as e:
            self.last_error = f"获取 AIHub 列表失败: {e}"

        stats_by_code = {}
        try:
            s_resp = requests.get(self.USAGE_STATS_URL, headers=headers, timeout=timeout)
            if s_resp.status_code == 200:
                stats_items = s_resp.json().get("data", {}).get("items", [])
                stats_by_code = {it.get("code"): it for it in stats_items if it.get("code")}
        except Exception:
            pass

        # 3. Filter candidates: rate_multiplier <= 0.2 and available
        candidates = []
        pelican_candidates = []

        for it in providers_raw:
            mult = it.get("rate_multiplier")
            code = it.get("code", "")
            is_avail = it.get("available", False)

            # Check for pelican test image artifacts
            dm = it.get("detection_media")
            if dm and isinstance(dm, dict):
                pres = dm.get("presentation", {})
                img = pres.get("image", {})
                if img.get("status") == "successful" and img.get("url"):
                    p_id = str(dm.get("id"))
                    pub_at = dm.get("published_at")
                    img_url = "https://aihub.top" + img.get("url")
                    pelican_candidates.append({
                        "id": p_id,
                        "published_at": pub_at,
                        "published_at_str": format_iso_timestamp(pub_at),
                        "model_code": code,
                        "url": img_url,
                        "title": img.get("title", {}).get("zh", "鹈鹕测试"),
                    })

            # Filter for active candidates with multiplier <= 0.2
            if mult is not None and mult <= 0.2:
                # Merge live usage stats
                stat = stats_by_code.get(code, {})
                ttft_ms = stat.get("avg_ttft_ms") or it.get("user_avg_ttft_ms") or it.get("avg_ttft_ms")
                ttft_str = f"{ttft_ms/1000:.1f}s" if ttft_ms else "--"
                cache_hit = it.get("cache_hit_rate", "-")
                if isinstance(cache_hit, (float, int)):
                    cache_hit = f"{cache_hit*100:.1f}%"

                candidates.append({
                    "code": code,
                    "rate_multiplier": mult,
                    "multiplier_str": f"{mult:.2f}x",
                    "cache_hit_rate": cache_hit,
                    "avg_ttft_ms": ttft_ms,
                    "ttft_str": ttft_str,
                    "available": is_avail,
                    "has_pelican": bool(dm and dm.get("presentation", {}).get("image", {}).get("status") == "successful"),
                })

        # Sort candidates: Available first, then rate multiplier ascending
        candidates.sort(key=lambda x: (not x["available"], x["rate_multiplier"]))
        top_groups = candidates[:4]

        # Process top 5 Pelican test images
        pelican_candidates.sort(key=lambda x: x["published_at"] or "", reverse=True)
        top_5_pelicans = pelican_candidates[:5]

        # Download & cache images locally in background/sync
        for item in top_5_pelicans:
            local_filename = f"pelican_{item['id']}.png"
            local_filepath = os.path.join(self.cache_dir, local_filename)
            item["local_path"] = local_filepath
            if not os.path.exists(local_filepath) or os.path.getsize(local_filepath) == 0:
                try:
                    img_resp = requests.get(item["url"], headers=headers, timeout=6)
                    if img_resp.status_code == 200:
                        with open(local_filepath, "wb") as f:
                            f.write(img_resp.content)
                except Exception:
                    pass

        self.cached_providers = top_groups
        self.cached_pelicans = top_5_pelicans
        self.last_fetch_time = now

        return {
            "success": True,
            "balance": balance,
            "top_groups": top_groups,
            "pelican_images": top_5_pelicans,
            "updated_at": time.strftime("%H:%M:%S", time.localtime(now)),
        }
