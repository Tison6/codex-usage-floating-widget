"""
Square API Relay Client (https://api.squarefaceicon.org).
Real-time monitors public model pricing, group ratios, descriptions, performance benchmarks, and user balance.
Supports user-defined group and model filtering with full metrics.
"""

import os
import json
import time
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


def format_tps(val: Optional[float]) -> str:
    """Format TPS matching official web frontend."""
    if val is None or val <= 0:
        return "—"
    if val >= 1000:
        return f"{val/1000:.1f}K t/s"
    if val < 10:
        return f"{val:.2f} t/s"
    return f"{val:.1f} t/s"


def format_duration(ms: Optional[float]) -> str:
    """Format latency / TTFT in seconds or ms matching official web frontend."""
    if ms is None or ms <= 0:
        return "—"
    if ms >= 1000:
        return f"{ms/1000:.2f}s"
    return f"{round(ms)}ms"



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
    "ds-v4.1可用",
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

# Default mapping of group to primary monitored focus model
DEFAULT_GROUP_MODELS = {
    "gpt-已过鹈鹕测试不降智": "gpt-6-astra",
    "混池优惠": "gpt-6-astra",
    "gpt-特惠分组": "gpt-6-astra",
    "pro专享": "gpt-6-astra",
    "terra分组": "gpt-6-astra",
    "限制宽松gpt": "gpt-6-astra",
    "ds-v4.1可用": "deepseek-v4.1-flash",
    "ds-v4没有4.1，4.1有专门分组": "deepseek-v4.1-flash",
    "ds-v4.1": "deepseek-v4.1-flash",
    "cc1": "claude-opus-5-5",
    "claude-ultra": "claude-ultra",
    "官方max": "gpt-5.5",
    "aws-cc": "claude-opus-5-5",
}

# Real benchmarks strictly matching Square official website modal data ([详情 >])
PERFORMANCE_BENCHMARKS = {
    "gpt-已过鹈鹕测试不降智": {
        "short_name": "已过鹈鹕",
        "color": "#10B981",
        "tps": "35.6 t/s",
        "ttft": "7.48s",
        "latency": "26.39s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "gpt-特惠分组": {
        "short_name": "特惠分组",
        "color": "#38BDF8",
        "tps": "32.5 t/s",
        "ttft": "4.67s",
        "latency": "21.19s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "pro专享": {
        "short_name": "pro专享",
        "color": "#F59E0B",
        "tps": "31.8 t/s",
        "ttft": "4.62s",
        "latency": "21.02s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "terra分组": {
        "short_name": "terra",
        "color": "#A78BFA",
        "tps": "44.9 t/s",
        "ttft": "4.69s",
        "latency": "16.36s",
        "success_rate": 100.0,
        "bar_count": 6,
    },
    "混池优惠": {
        "short_name": "混池优惠",
        "color": "#EAB308",
        "tps": "29.5 t/s",
        "ttft": "9.82s",
        "latency": "26.56s",
        "success_rate": 90.1,
        "bar_count": 6,
    },
    "限制宽松gpt": {
        "short_name": "宽松gpt",
        "color": "#38BDF8",
        "tps": "32.5 t/s",
        "ttft": "4.02s",
        "latency": "16.35s",
        "success_rate": 100.0,
        "bar_count": 6,
    },
    "claude-ultra": {
        "short_name": "ultra",
        "color": "#EC4899",
        "tps": "38.2 t/s",
        "ttft": "3.10s",
        "latency": "14.20s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "官方max": {
        "short_name": "官方max",
        "color": "#10B981",
        "tps": "52.0 t/s",
        "ttft": "2.40s",
        "latency": "11.50s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "aws-cc": {
        "short_name": "aws-cc",
        "color": "#38BDF8",
        "tps": "41.5 t/s",
        "ttft": "3.80s",
        "latency": "15.60s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "ds-v4没有4.1，4.1有专门分组": {
        "short_name": "4.1专门",
        "color": "#10B981",
        "tps": "68.4 t/s",
        "ttft": "1.25s",
        "latency": "8.40s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "ds-v4.1可用": {
        "short_name": "4.1可用",
        "color": "#10B981",
        "tps": "68.4 t/s",
        "ttft": "1.25s",
        "latency": "8.40s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "ds-v4.1": {
        "short_name": "ds-v4.1",
        "color": "#38BDF8",
        "tps": "62.1 t/s",
        "ttft": "1.45s",
        "latency": "9.10s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
    "cc1": {
        "short_name": "cc1",
        "color": "#38BDF8",
        "tps": "32.0 t/s",
        "ttft": "5.00s",
        "latency": "18.00s",
        "success_rate": 100.0,
        "bar_count": 16,
    },
}


class SquareAPIClient:
    """Client for fetching live Square API groups, pricing, and user usage."""

    GROUPS_URL = "https://api.squarefaceicon.org/api/user/groups"
    PRICING_URL = "https://api.squarefaceicon.org/api/pricing"
    USAGE_URL = "https://api.squarefaceicon.org/dashboard/billing/usage"
    PERF_URL = "https://api.squarefaceicon.org/api/perf-metrics"

    def __init__(self, api_key: Optional[str] = None, config=None):
        self.config = config
        self.api_key = api_key or self._get_key_from_cc_switch()
        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: float = 0
        self.perf_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

        self.session = requests.Session()
        self.session.trust_env = False
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def fetch_model_perf(self, model_name: str, hours: int = 24, timeout: int = 5) -> Dict[str, Dict[str, Any]]:
        """
        Fetch 24h performance metrics for a specific model (TPS, TTFT, Latency, Success Rate, Series).
        Follows the exact web Pricing model details Performance tab logic (/pricing/$modelId -> /api/perf-metrics?model=...).
        """
        now = time.time()
        if model_name in self.perf_cache:
            cached_time, cached_val = self.perf_cache[model_name]
            if now - cached_time < 60:
                return cached_val

        resp_data = None
        # Try direct session first
        try:
            r = self.session.get(self.PERF_URL, params={"model": model_name, "hours": hours}, timeout=timeout)
            if r.status_code == 200:
                resp_data = r.json()
        except Exception:
            pass

        # Try fallback with proxy if direct fails
        if not resp_data or not resp_data.get("success"):
            try:
                s_fallback = requests.Session()
                r = s_fallback.get(self.PERF_URL, params={"model": model_name, "hours": hours}, timeout=timeout)
                if r.status_code == 200:
                    resp_data = r.json()
            except Exception:
                pass

        if not resp_data or not resp_data.get("success"):
            if model_name in self.perf_cache:
                return self.perf_cache[model_name][1]
            return {}

        groups = resp_data.get("data", {}).get("groups", [])
        parsed: Dict[str, Dict[str, Any]] = {}
        for g in groups:
            g_name = g.get("group")
            if not g_name:
                continue
            tps_val = float(g.get("avg_tps", 0.0) or 0.0)
            ttft_val = float(g.get("avg_ttft_ms", 0.0) or 0.0)
            lat_val = float(g.get("avg_latency_ms", 0.0) or 0.0)
            sr_val = float(g.get("success_rate", 100.0) or 0.0)
            series = g.get("series", [])
            parsed[g_name] = {
                "tps": format_tps(tps_val),
                "ttft": format_duration(ttft_val),
                "latency": format_duration(lat_val),
                "success_rate": round(sr_val, 1),
                "series": series,
                "bar_count": len(series) if series else 16,
                "avg_tps": tps_val,
                "avg_ttft_ms": ttft_val,
                "avg_latency_ms": lat_val,
            }
        self.perf_cache[model_name] = (now, parsed)
        return parsed


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

    def get_group_models_mapping(self) -> Dict[str, str]:
        """Get mapping of group_name -> focused_model_name."""
        if self.config:
            m = self.config.get("square_group_models")
            if m and isinstance(m, dict):
                return m
        return dict(DEFAULT_GROUP_MODELS)

    def set_group_models_mapping(self, mapping: Dict[str, str]):
        """Save group_name -> focused_model_name mapping."""
        if self.config:
            self.config.set("square_group_models", mapping)

    def fetch_data(self, force: bool = False, timeout: int = 5) -> Dict[str, Any]:
        """
        Fetch real-time public groups, models, and user balance from Square API.
        Computes dynamic mapping between selected groups and selected models with performance metrics.
        """
        now = time.time()
        if not force and self.cached_data and (now - self.last_fetch_time < 30):
            return self.cached_data

        # 1. Fetch live groups
        raw_groups: Dict[str, Any] = {}
        try:
            r_g = self.session.get(self.GROUPS_URL, timeout=timeout)
            r_g.encoding = "utf-8"
            if r_g.status_code == 200:
                raw_groups = r_g.json().get("data", {})
        except Exception:
            pass

        # 2. Fetch live models and pricing
        raw_models: List[Dict[str, Any]] = []
        try:
            r_p = self.session.get(self.PRICING_URL, timeout=timeout)
            r_p.encoding = "utf-8"
            if r_p.status_code == 200:
                raw_models = r_p.json().get("data", [])
        except Exception:
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
                }
                usage_resp = self.session.get(self.USAGE_URL, headers=auth_headers, timeout=timeout)
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

        # 4. Determine user selections and mapping
        selected_group_names = self.get_selected_groups()
        selected_model_names = self.get_selected_models()
        group_models_mapping = self.get_group_models_mapping()

        # 5. Fetch live 24h performance metrics for monitored/mapped models from /api/perf-metrics
        needed_models = (
            set(selected_model_names)
            | set(group_models_mapping.values())
            | set(DEFAULT_GROUP_MODELS.values())
            | {"gpt-6-astra", "deepseek-v4.1-flash", "claude-opus-5-5", "gpt-5.5"}
        )
        needed_models.discard(None)
        needed_models.discard("")

        model_perf_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        if needed_models:
            with ThreadPoolExecutor(max_workers=min(len(needed_models), 6)) as executor:
                future_to_m = {executor.submit(self.fetch_model_perf, m): m for m in needed_models}
                for fut in as_completed(future_to_m):
                    m_name = future_to_m[fut]
                    try:
                        model_perf_map[m_name] = fut.result()
                    except Exception:
                        model_perf_map[m_name] = {}

        def get_group_bench(g_name: str, target_model: Optional[str] = None) -> Dict[str, Any]:
            # Try target model first if specified
            if target_model and target_model in model_perf_map:
                if g_name in model_perf_map[target_model]:
                    return model_perf_map[target_model][g_name]
            # Try mapped model
            mapped_m = group_models_mapping.get(g_name) or DEFAULT_GROUP_MODELS.get(g_name)
            if mapped_m and mapped_m in model_perf_map:
                if g_name in model_perf_map[mapped_m]:
                    return model_perf_map[mapped_m][g_name]
            # Try any other fetched model that has data for this group
            for m_perf in model_perf_map.values():
                if g_name in m_perf:
                    return m_perf[g_name]
            # Fallback to static baseline benchmarks
            return PERFORMANCE_BENCHMARKS.get(g_name, {})

        # 6. Prepare all available groups and models for selection dialog
        all_groups = []
        for g_name, g_info in raw_groups.items():
            ratio = float(g_info.get("ratio", 1.0))
            static_def = PERFORMANCE_BENCHMARKS.get(g_name, {})
            live_bench = get_group_bench(g_name)
            short_name = static_def.get("short_name", g_name[:6])
            color = static_def.get("color") or ("#10B981" if ratio < 0.2 else ("#38BDF8" if ratio < 0.4 else "#F59E0B"))

            all_groups.append({
                "name": g_name,
                "short_name": short_name,
                "color": color,
                "ratio": ratio,
                "ratio_str": f"{ratio:.2f}x",
                "desc": g_info.get("desc", ""),
                "tps": live_bench.get("tps") or static_def.get("tps", "32.0 t/s"),
                "ttft": live_bench.get("ttft") or static_def.get("ttft", "5.00s"),
                "latency": live_bench.get("latency") or static_def.get("latency", "18.00s"),
                "success_rate": live_bench.get("success_rate") if live_bench.get("success_rate") is not None else static_def.get("success_rate", 100.0),
                "series": live_bench.get("series", []),
                "bar_count": live_bench.get("bar_count", static_def.get("bar_count", 16)),
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

        # 7. Build dynamic monitored rows based on user's active selections
        monitored_rows = []
        for g_name in selected_group_names:
            g_info = raw_groups.get(g_name)
            if not g_info:
                continue

            ratio = float(g_info.get("ratio", 1.0))
            desc = g_info.get("desc", "")
            static_def = PERFORMANCE_BENCHMARKS.get(g_name, {})
            short_name = static_def.get("short_name", g_name[:6])
            color = static_def.get("color") or ("#10B981" if ratio < 0.2 else ("#38BDF8" if ratio < 0.4 else "#F59E0B"))

            # Find matching models that user checked AND that belong to this group
            matching_models = []
            for m in raw_models:
                m_name = m.get("model_name", "")
                if m_name in selected_model_names:
                    enable_groups = m.get("enable_groups", [])
                    if g_name in enable_groups:
                        m_ratio = float(m.get("model_ratio", 1.0))
                        effective_ratio = ratio * m_ratio
                        disp_name = MODEL_DISPLAY_NAMES.get(m_name, m_name)
                        matching_models.append({
                            "name": m_name,
                            "display_name": disp_name,
                            "model_ratio": m_ratio,
                            "effective_ratio": effective_ratio,
                            "breakdown": f"{disp_name} (官网倍率 {m_ratio}x × 分组 {ratio}x = 综合 {effective_ratio:.3f}x)",
                        })

            # Focus model for this group (either mapped, or first matching checked model, or default)
            target_model_code = group_models_mapping.get(g_name)

            focus_model_obj = None
            if target_model_code:
                focus_model_obj = next((m for m in matching_models if m["name"] == target_model_code), None)
                if not focus_model_obj:
                    # Look in raw_models
                    raw_m = next((m for m in raw_models if m.get("model_name") == target_model_code), None)
                    if raw_m:
                        m_ratio = float(raw_m.get("model_ratio", 1.0))
                        effective_ratio = ratio * m_ratio
                        disp_name = MODEL_DISPLAY_NAMES.get(target_model_code, target_model_code)
                        focus_model_obj = {
                            "name": target_model_code,
                            "display_name": disp_name,
                            "model_ratio": m_ratio,
                            "effective_ratio": effective_ratio,
                            "breakdown": f"{disp_name} (官网 {m_ratio}x × 分组 {ratio}x = 综合 {effective_ratio:.2f}x)",
                        }
            if not focus_model_obj and matching_models:
                focus_model_obj = matching_models[0]
            if not focus_model_obj:
                def_code = DEFAULT_GROUP_MODELS.get(g_name, "gpt-6-astra")
                disp_name = MODEL_DISPLAY_NAMES.get(def_code, def_code)
                focus_model_obj = {
                    "name": def_code,
                    "display_name": disp_name,
                    "model_ratio": 1.0,
                    "effective_ratio": ratio,
                    "breakdown": f"{disp_name} (综合 {ratio:.2f}x)",
                }

            live_bench = get_group_bench(g_name, target_model=focus_model_obj["name"])

            monitored_rows.append({
                "group_name": g_name,
                "short_name": short_name,
                "color": color,
                "ratio": ratio,
                "ratio_str": f"{ratio:.2f}x",
                "desc": desc,
                "tps": live_bench.get("tps") or static_def.get("tps", "32.0 t/s"),
                "ttft": live_bench.get("ttft") or static_def.get("ttft", "5.00s"),
                "latency": live_bench.get("latency") or static_def.get("latency", "18.00s"),
                "success_rate": live_bench.get("success_rate") if live_bench.get("success_rate") is not None else static_def.get("success_rate", 100.0),
                "series": live_bench.get("series", []),
                "bar_count": live_bench.get("bar_count", static_def.get("bar_count", 16)),
                "focus_model": focus_model_obj["name"],
                "focus_model_display": focus_model_obj["display_name"],
                "effective_ratio": focus_model_obj["effective_ratio"],
                "effective_ratio_str": f"{focus_model_obj['effective_ratio']:.2f}x",
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
            "group_models_mapping": self.get_group_models_mapping(),
        }

        self.cached_data = result
        self.last_fetch_time = now
        return result

