"""
AIHub Relay Client (https://aihub.top).
Monitors low-multiplier provider groups, live latency, cache rates, success rates, and pelican test images.
Supports user-defined provider selection with real-time parameter filtering.
"""

import os
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import requests


def format_iso_timestamp(iso_str: Optional[str]) -> str:
    """Format ISO 8601 timestamp to readable local string."""
    if not iso_str:
        return ""
    try:
        clean_str = iso_str.split(".")[0]
        if "+" in iso_str:
            dt = datetime.fromisoformat(iso_str)
        elif "Z" in iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%m-%d %H:%M:%S")
    except Exception:
        try:
            return iso_str[5:19].replace("T", " ")
        except Exception:
            return iso_str


# Default recommended providers matching user selection
DEFAULT_SELECTED_PROVIDERS = [
    "A018-Plus/K12",
    "A031-Pro",
]

# Default filter thresholds for automatic mode (按默认值)
DEFAULT_FILTER_MIN_SR = 80.0
DEFAULT_FILTER_MIN_CACHE = 80.0
DEFAULT_FILTER_MAX_EFF = 0.25
DEFAULT_FILTER_MAX_NOM = 0.25


class AIHubClient:
    """Client for querying AIHub provider metrics, cache rate, success rate, and pelican test images."""

    BASE_URL = "https://aihub.dog"
    PROVIDERS_URL = "https://aihub.dog/api/v1/public/providers"
    USAGE_STATS_URL = "https://aihub.dog/api/v1/public/groups/usage-stats"

    def __init__(self, config=None, cache_dir: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None, **kwargs):
        self.config = config
        self.email = email
        self.password = password
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pelican_cache"
        )
        os.makedirs(self.cache_dir, exist_ok=True)

        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: float = 0
        self.last_error: str = ""

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        self.history_metadata_cache: Dict[int, Any] = {}
        self._auto_mode_override: Optional[bool] = None

    def get_auto_mode(self) -> bool:
        """Get whether AIHub is in automatic filter mode (vs manual selection)."""
        if self._auto_mode_override is not None:
            return self._auto_mode_override
        if self.config:
            val = self.config.get("aihub_auto_mode")
            if val is not None:
                return bool(val)
        return True  # Default to auto mode

    def set_auto_mode(self, auto: bool):
        """Set whether AIHub is in automatic filter mode."""
        self._auto_mode_override = bool(auto)
        if self.config:
            self.config.set("aihub_auto_mode", bool(auto))

    def get_selected_providers(self) -> List[str]:
        """Get list of user-selected provider codes."""
        if self.config:
            sel = self.config.get("aihub_selected_providers")
            if sel and isinstance(sel, list):
                return sel
        return list(DEFAULT_SELECTED_PROVIDERS)

    def set_selected_providers(self, providers: List[str]):
        """Save user-selected provider codes."""
        if self.config:
            self.config.set("aihub_selected_providers", providers)

    def fetch_data(self, force: bool = False, timeout: int = 8) -> Dict[str, Any]:
        """
        Fetch public providers and live usage stats from AIHub.
        Parses multiplier, cache rate, TTFT, TPS, success rate, and test images.
        """
        now = time.time()
        if not force and self.cached_data and (now - self.last_fetch_time < 30):
            return self.cached_data

        providers_raw = []
        try:
            resp = self.session.get(self.PROVIDERS_URL, timeout=timeout)
            if resp.status_code == 200:
                providers_raw = resp.json().get("data", {}).get("items", [])
        except Exception as e:
            self.last_error = f"获取 AIHub 列表失败: {e}"

        stats_by_code = {}
        try:
            s_resp = self.session.get(self.USAGE_STATS_URL, timeout=timeout)
            if s_resp.status_code == 200:
                stats_items = s_resp.json().get("data", {}).get("items", [])
                stats_by_code = {it.get("code"): it for it in stats_items if it.get("code")}
        except Exception:
            pass

        # Load operator history for pelican images
        history_file = os.path.join(self.cache_dir, "pelican_history.json")
        operator_history: Dict[str, List[Dict[str, Any]]] = {}
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    operator_history = json.load(f)
            except Exception:
                pass

        all_parsed_providers = []
        for it in providers_raw:
            code = it.get("code", "")
            mult = it.get("rate_multiplier")
            if mult is None:
                continue

            # Exclude providers that are hidden from the provider hall or offline (e.g. B005)
            if it.get("visible_in_hall") is False or it.get("available") is False:
                continue

            is_avail = bool(it.get("available", False))

            # Cache hit rate
            cache_hit = it.get("cache_hit_rate", "-")
            cache_hit_str = "-"
            cache_hit_val = 0.0
            if isinstance(cache_hit, (float, int)):
                cache_hit_val = float(cache_hit) * 100.0 if float(cache_hit) <= 1.0 else float(cache_hit)
                cache_hit_str = f"{cache_hit_val:.1f}%"
            elif isinstance(cache_hit, str) and "%" in cache_hit:
                try:
                    cache_hit_val = float(cache_hit.replace("%", "").strip())
                    cache_hit_str = f"{cache_hit_val:.1f}%"
                except Exception:
                    pass

            # TTFT
            stat = stats_by_code.get(code, {})
            ttft_ms = it.get("avg_ttft_ms") or it.get("user_avg_ttft_ms") or stat.get("avg_ttft_ms")
            ttft_str = f"{ttft_ms/1000:.1f}s" if ttft_ms else "--"

            # TPS
            tps_val = it.get("output_tps")
            tps_str = f"{tps_val:.1f} t/s" if tps_val else "--"

            # Success rate: calculate from sr24h or probe_success_rate_6h
            sr_obj = it.get("success_rates") or {}
            sr_val = None
            if isinstance(sr_obj, dict):
                sr_val = sr_obj.get("24h") or sr_obj.get("6h")
            if sr_val is None:
                sr_val = it.get("probe_success_rate_6h")

            if sr_val is not None:
                sr_percent = round(float(sr_val) * 100, 1)
                sr_str = f"{sr_percent:.1f}%"
            else:
                sr_percent = 100.0
                sr_str = "100.0%"

            # Real / Effective Multiplier (official AIHub effective_multiplier factoring in caching)
            eff_mult = it.get("effective_multiplier")
            eff_ready = bool(it.get("effective_multiplier_ready", False))
            if eff_mult is not None and isinstance(eff_mult, (int, float)):
                eff_mult_val = float(eff_mult)
                eff_mult_str = f"{eff_mult_val:.2f}x"
            else:
                eff_mult_val = float(mult)
                eff_mult_str = f"{mult:.2f}x"

            # Detection media / image
            dm = it.get("detection_media") or {}
            pres = dm.get("presentation") or {}
            img = pres.get("image") or {}
            img_url = img.get("url")
            full_img_url = (f"{self.BASE_URL}{img_url}") if img_url else ""
            group_id = it.get("group_id")

            # Model verification / detection (是否通过 / 疑似 / 其他)
            md = it.get("model_detection") or {}
            md_status = md.get("status")  # 'passed', 'suspected', 'insufficient_evidence', 'not_configured', 'detection_failed', None
            md_model = md.get("model", "")
            md_reason = md.get("user_reason", "")
            md_time = format_iso_timestamp(md.get("detected_at"))

            if md_status == "passed":
                det_status = "passed"
                det_label = "通过"
                det_color = "#10B981"
                det_dot = "🟢"
                det_tip = f"模型检测: 🟢 通过\n测试目标: {md_model or '默认'}\n说明: {md_reason or '官方验证通过'}"
                if md_time:
                    det_tip += f"\n检测时间: {md_time}"
            elif md_status == "suspected":
                det_status = "suspected"
                det_label = "疑似"
                det_color = "#F59E0B"
                det_dot = "🟠"
                det_tip = f"模型检测: 🟠 疑似 (存疑)\n测试目标: {md_model or '默认'}\n说明: {md_reason or '验证无法定论'}"
                if md_time:
                    det_tip += f"\n检测时间: {md_time}"
            elif md_status == "insufficient_evidence":
                det_status = "other"
                det_label = "待定"
                det_color = "#64748B"
                det_dot = "⚪"
                det_tip = f"模型检测: ⚪ 证据不足 (无法定论)\n测试目标: {md_model or '默认'}\n说明: {md_reason or '暂无定论'}"
                if md_time:
                    det_tip += f"\n检测时间: {md_time}"
            elif md_status == "detection_failed":
                det_status = "other"
                det_label = "失败"
                det_color = "#64748B"
                det_dot = "⚪"
                det_tip = f"模型检测: ⚪ 检测失败\n说明: {md_reason or '检测暂时不可用'}"
            else:
                det_status = "other"
                det_label = "未检"
                det_color = "#475569"
                det_dot = "⚪"
                det_tip = "模型检测: ⚪ 未配置 / 暂无检测数据"

            all_parsed_providers.append({
                "code": code,
                "group_id": group_id,
                "rate_multiplier": mult,
                "multiplier_str": f"{mult:.2f}x",
                "effective_multiplier": eff_mult_val,
                "effective_multiplier_str": eff_mult_str,
                "effective_multiplier_ready": eff_ready,
                "cache_hit_rate": cache_hit_str,
                "cache_hit_val": cache_hit_val,
                "ttft_str": ttft_str,
                "ttft_ms": ttft_ms or 99999,
                "tps_str": tps_str,
                "success_rate": sr_percent,
                "success_rate_str": sr_str,
                "available": is_avail,
                "has_image": bool(img_url),
                "image_url": full_img_url,
                "detection_status": det_status,
                "detection_label": det_label,
                "detection_color": det_color,
                "detection_dot": det_dot,
                "detection_tip": det_tip,
                "detection_model": md_model,
                "detection_raw_status": md_status,
            })

        # Sort all providers: available first, then lower rate multiplier ascending
        all_parsed_providers.sort(key=lambda x: (not x["available"], x["rate_multiplier"]))

        # Determine monitored rows based on auto/manual mode
        is_auto = self.get_auto_mode()
        selected_codes = self.get_selected_providers() or []

        if is_auto:
            # Automatic mode: dynamically filter matching default thresholds (updated every minute)
            # 成功率 >= 80%, 缓存率 >= 80%, 真实倍率 <= 0.25, 标准倍率 <= 0.25
            matched_providers = [
                p for p in all_parsed_providers
                if p["available"]
                and p["success_rate"] >= DEFAULT_FILTER_MIN_SR
                and p["cache_hit_val"] >= DEFAULT_FILTER_MIN_CACHE
                and p["effective_multiplier"] <= DEFAULT_FILTER_MAX_EFF
                and p["rate_multiplier"] <= DEFAULT_FILTER_MAX_NOM
            ]
            if matched_providers:
                monitored_rows = matched_providers
            else:
                # Graceful fallback: pick top available providers with high SR
                monitored_rows = [p for p in all_parsed_providers if p["available"] and p["success_rate"] >= DEFAULT_FILTER_MIN_SR][:5]
                if not monitored_rows:
                    monitored_rows = all_parsed_providers[:5]
        else:
            # Manual mode: use user's checked providers
            monitored_rows = [p for p in all_parsed_providers if p["code"] in selected_codes]
            if not monitored_rows:
                monitored_rows = all_parsed_providers[:5]

        result = {
            "success": True,
            "auto_mode": is_auto,
            "all_providers": all_parsed_providers,
            "monitored_providers": monitored_rows,
            "top_groups": monitored_rows,
            "selected_codes": selected_codes,
            "updated_at": time.strftime("%H:%M:%S", time.localtime(now)),
        }

        self.cached_data = result
        self.last_fetch_time = now
        return result

    def get_provider_history_images(self, group_id: int, max_items: int = 60, ttl: int = 60) -> List[Dict[str, Any]]:
        """
        Online fetch of all historical pelican images for the provider from /api/v2/public/providers/{group_id}/images.
        Returns image items without downloading them to disk.
        Cached in-memory for `ttl` seconds to eliminate network lag on repeated clicks.
        """
        now = time.time()
        if group_id in self.history_metadata_cache:
            ts, cached_items = self.history_metadata_cache[group_id]
            if now - ts < ttl:
                return cached_items

        url = f"{self.BASE_URL}/api/v2/public/providers/{group_id}/images"
        all_items = []
        cursor = None
        try:
            while len(all_items) < max_items:
                params = {"cursor": cursor} if cursor else {}
                resp = self.session.get(url, params=params, timeout=6)
                if resp.status_code != 200:
                    break
                data = resp.json().get("data", {})
                items = data.get("items", [])
                if not items:
                    break
                for it in items:
                    dm = it.get("presentation", {}).get("image", {})
                    img_u = dm.get("url")
                    if img_u:
                        all_items.append({
                            "id": str(it.get("id")),
                            "published_at": it.get("published_at"),
                            "published_at_str": format_iso_timestamp(it.get("published_at")),
                            "url": f"{self.BASE_URL}{img_u}",
                            "title": dm.get("title", {}).get("zh", "鹈鹕"),
                        })
                cursor = data.get("next_cursor")
                if not cursor:
                    break
            self.history_metadata_cache[group_id] = (now, all_items)
        except Exception as e:
            print("Error fetching provider history images:", e)
        return all_items
