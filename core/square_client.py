"""
Square API Relay Client (https://api.squarefaceicon.org).
Real-time monitors public model pricing, group ratios, descriptions, and user balance.
Supports user-defined group and model filtering.
"""

import os
import json
import time
from typing import Dict, Any, Optional, List
import requests


# Default recommended groups to monitor if user hasn't configured
DEFAULT_SELECTED_GROUPS = [
    "gpt-已过鹈鹕测试不降智",
    "gpt-特惠分组",
    "pro专享",
    "terra分组",
    "混池优惠",
    "claude-ultra",
    "官方max",
    "aws-cc",
    "ds-v4没有4.1，4.1有专门分组",
    "ds-v4.1",
]

# Default recommended models to monitor if user hasn't configured
DEFAULT_SELECTED_MODELS = [
    "gpt-6-astra",
    "claude-opus-5-5",
    "deepseek-v4.1-flash",
    "gpt-5.5",
]

# Friendly display names for common models
MODEL_DISPLAY_NAMES = {
    "gpt-6-astra": "GPT-6 Astra",
    "claude-opus-5-5": "Claude Opus 5.5",
    "deepseek-v4.1-flash": "DS-v4.1 Flash",
    "gpt-5.5": "GPT-5.5",
    "claude-sonnet-5": "Claude Sonnet 5",
    "gpt-5.6-terra": "GPT-5.6 Terra",
    "gpt-6-sol": "GPT-6 Sol",
    "claude-ultra": "Claude Ultra",
}


class SquareAPIClient:
    """Client for fetching live Square API groups, pricing, and user usage."""

    GROUPS_URL = "https://api.squarefaceicon.org/api/user/groups"
    PRICING_URL = "https://api.squarefaceicon.org/api/pricing"
    USAGE_URL = "https://api.squarefaceicon.org/dashboard/billing/usage"

    def __init__(self, api_key: Optional[str] = None, config=None):
        self.config = config
        self.api_key = api_key or self._get_key_from_cc_switch()
        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: float = 0

    def _get_key_from_cc_switch(self) -> Optional[str]:
        """Try to retrieve Square API key from CC Switch local database."""
        db_path = os.path.expanduser("~/.cc-switch/cc-switch.db")
        if not os.path.exists(db_path):
            return None
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT settings_config FROM providers WHERE name LIKE '%Square%' OR url LIKE '%square%'"
            )
            rows = cursor.fetchall()
            conn.close()
            for (settings_raw,) in rows:
                if not settings_raw:
                    continue
                try:
                    cfg = json.loads(settings_raw)
                    auth = cfg.get("auth", {})
                    key = auth.get("OPENAI_API_KEY") or auth.get("api_key")
                    if key:
                        return key
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def get_selected_groups(self) -> List[str]:
        """Get list of user-selected group names."""
        if self.config:
            sel = self.config.get("square_selected_groups")
            if sel and isinstance(sel, list):
                return sel
        return list(DEFAULT_SELECTED_GROUPS)

    def set_selected_groups(self, groups: List[str]):
        """Save user-selected group names."""
        if self.config:
            self.config.set("square_selected_groups", groups)

    def get_selected_models(self) -> List[str]:
        """Get list of user-selected model names."""
        if self.config:
            sel = self.config.get("square_selected_models")
            if sel and isinstance(sel, list):
                return sel
        return list(DEFAULT_SELECTED_MODELS)

    def set_selected_models(self, models: List[str]):
        """Save user-selected model names."""
        if self.config:
            self.config.set("square_selected_models", models)

    def fetch_data(self, force: bool = False, timeout: int = 6) -> Dict[str, Any]:
        """
        Fetch real-time public groups, models, and user balance from Square API.
        Computes dynamic mapping between selected groups and selected models.
        """
        now = time.time()
        if not force and self.cached_data and (now - self.last_fetch_time < 30):
            return self.cached_data

        headers = {"User-Agent": "Mozilla/5.0"}

        # 1. Fetch live groups
        raw_groups: Dict[str, Any] = {}
        try:
            r_g = requests.get(self.GROUPS_URL, headers=headers, timeout=timeout)
            r_g.encoding = "utf-8"
            if r_g.status_code == 200:
                raw_groups = r_g.json().get("data", {})
        except Exception as e:
            pass

        # 2. Fetch live models and pricing
        raw_models: List[Dict[str, Any]] = []
        try:
            r_p = requests.get(self.PRICING_URL, headers=headers, timeout=timeout)
            r_p.encoding = "utf-8"
            if r_p.status_code == 200:
                raw_models = r_p.json().get("data", [])
        except Exception as e:
            pass

        # 3. Fetch user balance if API key present
        balance_info = {"has_key": False, "total_usage": None}
        if not self.api_key:
            self.api_key = self._get_key_from_cc_switch()
        if self.api_key:
            balance_info["has_key"] = True
            try:
                auth_headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "Mozilla/5.0",
                }
                usage_resp = requests.get(self.USAGE_URL, headers=auth_headers, timeout=timeout)
                if usage_resp.status_code == 200:
                    u_data = usage_resp.json()
                    balance_info["total_usage"] = u_data.get("total_usage", 0.0)
            except Exception:
                pass

        if not raw_groups and not raw_models:
            if self.cached_data:
                return self.cached_data
            return {
                "success": False,
                "error": "连接 Square API 失败，请检查网络",
                "monitored_rows": [],
                "all_groups": [],
                "all_models": [],
            }

        # 4. Prepare all available groups and models for selection dialog
        all_groups = []
        for g_name, g_info in raw_groups.items():
            all_groups.append({
                "name": g_name,
                "ratio": float(g_info.get("ratio", 1.0)),
                "ratio_str": f"{float(g_info.get('ratio', 1.0)):.2f}x",
                "desc": g_info.get("desc", ""),
            })
        # Sort groups: lower ratio first
        all_groups.sort(key=lambda x: x["ratio"])

        all_models = []
        for m in raw_models:
            m_name = m.get("model_name", "")
            all_models.append({
                "name": m_name,
                "display_name": MODEL_DISPLAY_NAMES.get(m_name, m_name),
                "enable_groups": m.get("enable_groups", []),
                "model_ratio": float(m.get("model_ratio", 1.0)),
            })
        all_models.sort(key=lambda x: x["name"])

        # 5. Build dynamic monitored rows based on user's active selections
        selected_group_names = self.get_selected_groups()
        selected_model_names = self.get_selected_models()

        monitored_rows = []
        for g_name in selected_group_names:
            g_info = raw_groups.get(g_name)
            if not g_info:
                # If group name not in raw_groups yet, skip or show placeholder
                continue

            ratio = float(g_info.get("ratio", 1.0))
            desc = g_info.get("desc", "")

            # Find matching models that user checked AND that belong to this group
            matching_models = []
            for m in raw_models:
                m_name = m.get("model_name", "")
                if m_name in selected_model_names:
                    enable_groups = m.get("enable_groups", [])
                    if g_name in enable_groups:
                        matching_models.append({
                            "name": m_name,
                            "display_name": MODEL_DISPLAY_NAMES.get(m_name, m_name),
                        })

            monitored_rows.append({
                "group_name": g_name,
                "ratio": ratio,
                "ratio_str": f"{ratio:.2f}x",
                "desc": desc,
                "models": matching_models,
                "models_str": ", ".join([m["display_name"] for m in matching_models]) if matching_models else "（无勾选模型）",
            })

        result = {
            "success": True,
            "updated_at": time.strftime("%H:%M:%S", time.localtime(now)),
            "balance": balance_info,
            "monitored_rows": monitored_rows,
            "all_groups": all_groups,
            "all_models": all_models,
            "selected_groups": selected_group_names,
            "selected_models": selected_model_names,
        }

        self.cached_data = result
        self.last_fetch_time = now
        return result
