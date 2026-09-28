"""
Square API Relay Client (https://api.squarefaceicon.org).
Monitors public model pricing, group ratios, and user balance.
Focuses on gpt-6-astra (混池优惠, gpt-已过鹈鹕测试不降智), gpt-5.5, and deepseek-v4.1-flash.
"""

import os
import json
import time
from typing import Dict, Any, Optional, List
import requests


class SquareAPIClient:
    """Client for fetching Square API pricing, groups, and user account usage."""

    PRICING_URL = "https://api.squarefaceicon.org/api/pricing"
    SUBSCRIPTION_URL = "https://api.squarefaceicon.org/dashboard/billing/subscription"
    USAGE_URL = "https://api.squarefaceicon.org/dashboard/billing/usage"

    # Baseline official reference prices ($ / 1M tokens)
    BASELINE_PRICES = {
        "gpt-6-astra": {"input": 10.0, "output": 50.0},
        "gpt-5.5": {"input": 5.0, "output": 15.0},
        "deepseek-v4.1-flash": {"input": 0.14, "output": 0.28},
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self._get_key_from_cc_switch()
        self.cached_pricing: Optional[Dict[str, Any]] = None
        self.last_pricing_time: float = 0
        self.cached_balance: Optional[Dict[str, Any]] = None
        self.last_balance_time: float = 0

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

    def fetch_data(self, force: bool = False, timeout: int = 8) -> Dict[str, Any]:
        """
        Fetch public pricing and user balance for Square API.
        Returns aggregated dictionary for UI display.
        """
        now = time.time()
        
        # 1. Fetch public pricing
        pricing_data = self.cached_pricing
        if force or not pricing_data or (now - self.last_pricing_time > 60):
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(self.PRICING_URL, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    pricing_data = resp.json()
                    self.cached_pricing = pricing_data
                    self.last_pricing_time = now
            except Exception as e:
                pass

        # 2. Fetch user balance if API key is present
        balance_info = {"has_key": False, "total_usage_usd": None}
        if not self.api_key:
            self.api_key = self._get_key_from_cc_switch()
            
        if self.api_key:
            balance_info["has_key"] = True
            if force or not self.cached_balance or (now - self.last_balance_time > 60):
                try:
                    auth_headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "Mozilla/5.0",
                    }
                    usage_resp = requests.get(self.USAGE_URL, headers=auth_headers, timeout=timeout)
                    if usage_resp.status_code == 200:
                        u_data = usage_resp.json()
                        total_usage = u_data.get("total_usage", 0.0)
                        # total_usage is in cents or standard units depending on One-API
                        balance_info["total_usage"] = total_usage
                        self.cached_balance = balance_info
                        self.last_balance_time = now
                except Exception:
                    pass
            elif self.cached_balance:
                balance_info = self.cached_balance

        if not pricing_data or not pricing_data.get("success"):
            return {
                "success": False,
                "error": "获取 Square API 价格信息失败",
                "balance": balance_info,
                "models": [],
            }

        group_ratios = pricing_data.get("group_ratio", {})
        models_raw = pricing_data.get("data", [])

        # Parse target models
        models_result = []

        # Target 1: gpt-6-astra
        astra_item = next((m for m in models_raw if m.get("model_name") == "gpt-6-astra"), None)
        if astra_item:
            base_ratio = float(astra_item.get("model_ratio", 5.0))
            groups = []
            # Specific filter for user's desired groups
            target_groups = ["混池优惠", "gpt-已过鹈鹕测试不降智"]
            for g_name in target_groups:
                g_ratio = float(group_ratios.get(g_name, 0.25))
                eff_mult = round(base_ratio * g_ratio, 2)
                base_p = self.BASELINE_PRICES["gpt-6-astra"]
                inp_p = round(base_p["input"] * eff_mult, 2)
                out_p = round(base_p["output"] * eff_mult, 2)
                short_name = "鹈鹕保真" if "鹈鹕" in g_name else ("混池优惠" if "混池" in g_name else g_name)
                groups.append({
                    "name": short_name,
                    "raw_name": g_name,
                    "group_ratio": g_ratio,
                    "effective_multiplier": eff_mult,
                    "input_price_1m": inp_p,
                    "output_price_1m": out_p,
                    "is_pelican_verified": "鹈鹕" in g_name,
                })
            models_result.append({
                "model_id": "gpt-6-astra",
                "display_name": "GPT-6 Astra",
                "base_ratio": base_ratio,
                "groups": groups,
            })

        # Target 2: gpt-5.5
        gpt55_item = next((m for m in models_raw if m.get("model_name") == "gpt-5.5"), None)
        if gpt55_item:
            base_ratio = float(gpt55_item.get("model_ratio", 2.5))
            enable_groups = gpt55_item.get("enable_groups", [])
            groups = []
            # Select top relevant groups: 混池优惠, gpt-特惠分组, codex
            priority_groups = ["混池优惠", "gpt-特惠分组", "codex", "terra车"]
            for g_name in priority_groups:
                if g_name in enable_groups or g_name in group_ratios:
                    g_ratio = float(group_ratios.get(g_name, 0.25))
                    eff_mult = round(base_ratio * g_ratio, 2)
                    base_p = self.BASELINE_PRICES["gpt-5.5"]
                    inp_p = round(base_p["input"] * eff_mult, 2)
                    out_p = round(base_p["output"] * eff_mult, 2)
                    short_name = "特惠分组" if "特惠" in g_name else ("混池优惠" if "混池" in g_name else g_name)
                    groups.append({
                        "name": short_name,
                        "raw_name": g_name,
                        "group_ratio": g_ratio,
                        "effective_multiplier": eff_mult,
                        "input_price_1m": inp_p,
                        "output_price_1m": out_p,
                        "is_pelican_verified": False,
                    })
            models_result.append({
                "model_id": "gpt-5.5",
                "display_name": "OpenAI 5.5",
                "base_ratio": base_ratio,
                "groups": groups[:2],  # keep top 2 for compact view
            })

        # Target 3: deepseek-v4.1-flash
        ds_item = next(
            (m for m in models_raw if m.get("model_name") == "deepseek-v4.1-flash"), None
        )
        if ds_item:
            base_ratio = float(ds_item.get("model_ratio", 1.0))
            groups = []
            ds_groups = ["ds-v4没有4.1，4.1有专门分组", "ds-v4.1"]
            for g_name in ds_groups:
                if g_name in group_ratios:
                    g_ratio = float(group_ratios.get(g_name, 0.1))
                    eff_mult = round(base_ratio * g_ratio, 3)
                    short_name = "4.1特惠" if "专门分组" in g_name else ("4.1通用" if "ds-v4.1" in g_name else g_name)
                    groups.append({
                        "name": short_name,
                        "raw_name": g_name,
                        "group_ratio": g_ratio,
                        "effective_multiplier": eff_mult,
                        "input_price_1m": round(0.14 * g_ratio, 3),
                        "output_price_1m": round(0.28 * g_ratio, 3),
                        "is_pelican_verified": False,
                    })
            models_result.append({
                "model_id": "deepseek-v4.1-flash",
                "display_name": "DS-v4.1 Flash",
                "base_ratio": base_ratio,
                "groups": groups,
            })

        return {
            "success": True,
            "updated_at": time.strftime("%H:%M:%S", time.localtime(now)),
            "balance": balance_info,
            "models": models_result,
        }
