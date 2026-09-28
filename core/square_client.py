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

        # 3. Parse target models and group ratios
        group_ratios = pricing_data.get("group_ratio", {})
        models_raw = pricing_data.get("data", [])

        # Helper to clean group names
        def get_group_ratio(name_key: str, default_val: float) -> float:
            for k, v in group_ratios.items():
                if name_key in k:
                    try:
                        return float(v)
                    except Exception:
                        pass
            return default_val

        # Models with actual group multipliers (NO base ratio multiplication)
        models_result = []

        # Target 1: gpt-6-astra
        astra_item = next((m for m in models_raw if m.get("model_name") == "gpt-6-astra"), None)
        if astra_item:
            ratio_pelican = get_group_ratio("鹈鹕", 0.25)
            ratio_hunchi = get_group_ratio("混池", 0.10)
            ratio_terra = get_group_ratio("terra", 0.15)
            ratio_pro = get_group_ratio("pro", 0.25)
            models_result.append({
                "model_id": "gpt-6-astra",
                "display_name": "GPT-6 Astra",
                "groups": [
                    {"name": "鹈鹕保真", "ratio_str": f"{ratio_pelican:.2f}x", "ratio": ratio_pelican, "verified": True},
                    {"name": "混池优惠", "ratio_str": f"{ratio_hunchi:.2f}x", "ratio": ratio_hunchi, "verified": False},
                    {"name": "terra分组", "ratio_str": f"{ratio_terra:.2f}x", "ratio": ratio_terra, "verified": False},
                ]
            })

        # Target 2: Claude Opus 5.5 (User requested Opus 5.5 / OpenSSL 5.5, NOT OpenAI 5.5)
        opus_item = next((m for m in models_raw if m.get("model_name") == "claude-opus-5-5"), None)
        if opus_item:
            ratio_ultra = get_group_ratio("claude-ultra", 0.40)
            ratio_max = get_group_ratio("官方max", 0.60)
            ratio_aws = get_group_ratio("aws-cc", 0.40)
            models_result.append({
                "model_id": "claude-opus-5-5",
                "display_name": "Claude Opus 5.5",
                "groups": [
                    {"name": "ultra", "ratio_str": f"{ratio_ultra:.2f}x", "ratio": ratio_ultra, "verified": False},
                    {"name": "官方max", "ratio_str": f"{ratio_max:.2f}x", "ratio": ratio_max, "verified": False},
                    {"name": "aws-cc", "ratio_str": f"{ratio_aws:.2f}x", "ratio": ratio_aws, "verified": False},
                ]
            })

        # Target 3: deepseek-v4.1-flash
        ds_item = next((m for m in models_raw if m.get("model_name") == "deepseek-v4.1-flash"), None)
        if ds_item:
            ratio_special = get_group_ratio("4.1有专门分组", 0.08)
            ratio_std = get_group_ratio("ds-v4.1", 0.10)
            models_result.append({
                "model_id": "deepseek-v4.1-flash",
                "display_name": "DS-v4.1 Flash",
                "groups": [
                    {"name": "4.1特惠", "ratio_str": f"{ratio_special:.2f}x", "ratio": ratio_special, "verified": False},
                    {"name": "4.1通用", "ratio_str": f"{ratio_std:.2f}x", "ratio": ratio_std, "verified": False},
                ]
            })

        # 4. Group Performance Table (matching user screenshot with TPS, TTFT, Latency & Success rate bar)
        performance_groups = [
            {
                "raw_name": "gpt-已过鹈鹕测试不降智",
                "name": "已过鹈鹕测试不降智",
                "short_name": "已过鹈鹕",
                "color": "#10B981",  # Vibrant green
                "multiplier": f"{get_group_ratio('鹈鹕', 0.25):.2f}x",
                "tps": "32.9 t/s",
                "ttft": "7.63s",
                "latency": "21.62s",
                "success_rate": 100.0,
            },
            {
                "raw_name": "gpt-特惠分组",
                "name": "gpt-特惠分组",
                "short_name": "特惠分组",
                "color": "#38BDF8",  # Sky Blue
                "multiplier": f"{get_group_ratio('gpt-特惠', 0.25):.2f}x",
                "tps": "32.7 t/s",
                "ttft": "4.59s",
                "latency": "16.07s",
                "success_rate": 100.0,
            },
            {
                "raw_name": "pro专享",
                "name": "pro专享",
                "short_name": "pro专享",
                "color": "#F59E0B",  # Amber gold
                "multiplier": f"{get_group_ratio('pro专享', 0.25):.2f}x",
                "tps": "31.8 t/s",
                "ttft": "4.95s",
                "latency": "22.60s",
                "success_rate": 100.0,
            },
            {
                "raw_name": "terra分组",
                "name": "terra分组",
                "short_name": "terra分组",
                "color": "#A78BFA",  # Purple
                "multiplier": f"{get_group_ratio('terra', 0.15):.2f}x",
                "tps": "45.3 t/s",
                "ttft": "4.52s",
                "latency": "17.83s",
                "success_rate": 100.0,
            },
            {
                "raw_name": "混池优惠",
                "name": "混池优惠",
                "short_name": "混池优惠",
                "color": "#EAB308",  # Yellow
                "multiplier": f"{get_group_ratio('混池', 0.10):.2f}x",
                "tps": "27.6 t/s",
                "ttft": "13.22s",
                "latency": "28.90s",
                "success_rate": 98.6,
            },
        ]

        return {
            "success": True,
            "updated_at": time.strftime("%H:%M:%S", time.localtime(now)),
            "balance": balance_info,
            "models": models_result,
            "performance_groups": performance_groups,
        }
