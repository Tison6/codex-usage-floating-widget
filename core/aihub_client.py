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

    def get_excluded_providers(self) -> List[str]:
        """Get list of user-excluded (blacklisted) provider codes."""
        if self.config:
            exc = self.config.get("aihub_excluded_providers")
            if exc and isinstance(exc, list):
                return exc
        return []

    def set_excluded_providers(self, providers: List[str]):
        """Save user-excluded provider codes."""
        if self.config:
            self.config.set("aihub_excluded_providers", providers)

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

        # Load rolling metrics history for 1h/1d/7d averages
        metrics_history_file = os.path.join(os.path.dirname(self.cache_dir), "aihub_history.json")
        metrics_history: Dict[str, List[Dict[str, Any]]] = {}
        if os.path.exists(metrics_history_file):
            try:
                with open(metrics_history_file, "r", encoding="utf-8") as f:
                    metrics_history = json.load(f)
            except Exception:
                pass

        excluded_codes = set(self.get_excluded_providers() or [])
        all_parsed_providers = []
        for it in providers_raw:
            code = it.get("code", "")
            if not code:
                continue
            mult = it.get("rate_multiplier")
            if mult is None:
                mult = 1.0

            is_avail = bool(it.get("available", False))
            visible_in_hall = bool(it.get("visible_in_hall", False))
            error_cat = it.get("error_category") or ""

            # Cache hit rate
            cache_hit = it.get("cache_hit_rate", "-")
            cache_hit_str = "-"
            cache_hit_val = 0.0
            has_cache = False
            if isinstance(cache_hit, (float, int)):
                cache_hit_val = float(cache_hit) * 100.0 if float(cache_hit) <= 1.0 else float(cache_hit)
                cache_hit_str = f"{cache_hit_val:.1f}%"
                has_cache = True
            elif isinstance(cache_hit, str) and "%" in cache_hit:
                try:
                    cache_hit_val = float(cache_hit.replace("%", "").strip())
                    cache_hit_str = f"{cache_hit_val:.1f}%"
                    has_cache = True
                except Exception:
                    pass

            # TTFT
            stat = stats_by_code.get(code, {})
            ttft_ms = it.get("avg_ttft_ms") or it.get("user_avg_ttft_ms") or stat.get("avg_ttft_ms")
            ttft_str = f"{ttft_ms/1000:.1f}s" if ttft_ms else "--"

            # TPS
            tps_val = it.get("output_tps")
            tps_str = f"{tps_val:.1f} t/s" if tps_val else "--"

            # Success rate: calculate from 1h, then 24h, then 6h, or probe_success_rate_6h (must use is not None, not or, since 0% is valid!)
            sr_obj = it.get("success_rates") or {}
            sr_val = None
            if isinstance(sr_obj, dict) and sr_obj:
                for k in ["1h", "24h", "6h"]:
                    if sr_obj.get(k) is not None:
                        sr_val = sr_obj.get(k)
                        break
            if sr_val is None:
                sr_val = it.get("probe_success_rate_6h")

            if sr_val is not None:
                sr_percent = round(float(sr_val) * 100, 1)
                sr_str = f"{sr_percent:.1f}%"
                has_sr = True
            else:
                sr_percent = None
                sr_str = "--"
                has_sr = False

            # Real / Effective Multiplier (official AIHub effective_multiplier factoring in caching)
            eff_mult = it.get("effective_multiplier")
            eff_ready = bool(it.get("effective_multiplier_ready", False))
            eff_reason_raw = it.get("effective_multiplier_reason")
            reason_map = {
                "not_configured": "未配置",
                "insufficient_samples": "样本不足",
                "no_samples": "暂无样本",
                "no_input_spend": "暂无输入消费",
                "pricing_reference_unavailable": "参考不可用",
                "openrouter_reference_unavailable": "参考不可用",
                "runtime_window_not_ready": "尚未就绪",
                "runtime_metrics_stale": "数据过期",
                "openrouter_reference_stale": "参考已过期",
            }
            eff_reason_str = reason_map.get(eff_reason_raw, eff_reason_raw or "")
            if eff_mult is not None and isinstance(eff_mult, (int, float)) and eff_ready:
                eff_mult_val = float(eff_mult)
                eff_mult_str = f"{eff_mult_val:.2f}x"
            else:
                eff_mult_val = None
                eff_mult_str = "--"

            # 1M tokens effective input price (e.g. ¥0.12/M)
            price_1m = it.get("effective_input_price_per_million_1h")
            price_1m_str = f"¥{price_1m:.2f}/M" if price_1m is not None else "--"

            hist_items = metrics_history.get(code, [])
            hist_span = (now - hist_items[0]["t"]) if hist_items else 0

            # Multi-period success rates: 成功率(1h/1d/7d) e.g. 93%/88%/90%
            sr1h_samples = [h["sr"] for h in hist_items if h.get("sr") is not None and h["t"] >= now - 3600]
            sr1d_samples = [h["sr"] for h in hist_items if h.get("sr") is not None and h["t"] >= now - 86400]
            sr7d_samples = [h["sr"] for h in hist_items if h.get("sr") is not None and h["t"] >= now - 7 * 86400]

            s1h = sr_obj.get("1h") if isinstance(sr_obj, dict) else None
            s1d = (sr_obj.get("24h") if sr_obj.get("24h") is not None else sr_obj.get("1d")) if isinstance(sr_obj, dict) else None
            s7d = sr_obj.get("7d") if isinstance(sr_obj, dict) else None

            # 1h: Authoritative 1h success rate from AIHub API to match official website exactly
            if s1h is not None:
                s1h_val = float(s1h) * 100.0 if float(s1h) <= 1.0 else float(s1h)
                s1h_str = f"{round(s1h_val)}%"
            elif sr_percent is not None:
                s1h_str = f"{round(sr_percent)}%"
            elif sr1h_samples:
                s1h_str = f"{round(sum(sr1h_samples) / len(sr1h_samples))}%"
            else:
                s1h_str = "--"

            # 1d (24h): Prefer genuine API 24h if distinct from 1h, otherwise calculate from local continuous history
            if s1d is not None and s1h is not None and s1d != s1h:
                s1d_val = float(s1d) * 100.0 if float(s1d) <= 1.0 else float(s1d)
                s1d_str = f"{round(s1d_val)}%"
            elif sr1d_samples and len(sr1d_samples) >= 5 and hist_span >= 7200:
                s1d_str = f"{round(sum(sr1d_samples) / len(sr1d_samples))}%"
            else:
                s1d_str = s1h_str

            # 7d: Prefer genuine API 7d if distinct from 1h, otherwise calculate from local continuous history (requires >= 3 days)
            if s7d is not None and s1h is not None and s7d != s1h:
                s7d_val = float(s7d) * 100.0 if float(s7d) <= 1.0 else float(s7d)
                s7d_str = f"{round(s7d_val)}%"
            elif sr7d_samples and len(sr7d_samples) >= 10 and hist_span >= 86400 * 3:
                s7d_str = f"{round(sum(sr7d_samples) / len(sr7d_samples))}%"
            else:
                s7d_str = "--"

            sr_multi_str = f"{s1h_str}/{s1d_str}/{s7d_str}"

            # Multi-period cache hit rates: 缓存率(当前/1h/1d/7d) e.g. 87%/85%/90%/--
            c_cur_str = f"{round(cache_hit_val)}%" if has_cache else "-"
            c1h_samples = [h["cache"] for h in hist_items if h.get("cache") is not None and h["t"] >= now - 3600]
            c1d_samples = [h["cache"] for h in hist_items if h.get("cache") is not None and h["t"] >= now - 86400]
            c7d_samples = [h["cache"] for h in hist_items if h.get("cache") is not None and h["t"] >= now - 7 * 86400]

            # 1h cache hit rate: ALWAYS prefer official authoritative 1h cache rate from AIHub API (runtime_cache_1h)
            rc_1h = it.get("runtime_cache_1h") or {}
            c1h_raw = rc_1h.get("cache_hit_rate")
            if c1h_raw is None:
                c1h_raw = rc_1h.get("weighted_cache_hit_rate")
            if c1h_raw is None and has_cache:
                c1h_raw = cache_hit_val / 100.0

            if c1h_raw is not None:
                c1h_val = float(c1h_raw) * 100.0 if float(c1h_raw) <= 1.0 else float(c1h_raw)
                c1h_str = f"{round(c1h_val)}%"
            elif c1h_samples:
                c1h_str = f"{round(sum(c1h_samples) / len(c1h_samples))}%"
            else:
                c1h_str = c_cur_str if c_cur_str != "-" else "--"

            # 1d cache hit rate: Past 24h rolling average from local history if span >= 2 hours, else 1h
            if c1d_samples and len(c1d_samples) >= 5 and hist_span >= 7200:
                c1d_str = f"{round(sum(c1d_samples) / len(c1d_samples))}%"
            else:
                c1d_str = c1h_str

            # 7d cache hit rate: Past 7d rolling average from local history only if span >= 3 days (72 hours), else "--"
            if c7d_samples and len(c7d_samples) >= 10 and hist_span >= 86400 * 3:
                c7d_str = f"{round(sum(c7d_samples) / len(c7d_samples))}%"
            else:
                c7d_str = "--"

            cache_multi_str = f"{c_cur_str}/{c1h_str}/{c1d_str}/{c7d_str}"

            # Reference cache hit rate: reference_cache_hit_rate (官方 Sol 参考缓存率基准, 如 81%)
            rc_1h_obj = it.get("runtime_cache_1h") or {}
            cref_raw = rc_1h_obj.get("reference_cache_hit_rate")
            if cref_raw is not None:
                cref_val = float(cref_raw) * 100.0 if float(cref_raw) <= 1.0 else float(cref_raw)
                ref_cache_str = f"{round(cref_val)}%"
                ref_cache_val = cref_val
            else:
                ref_cache_str = "--"
                ref_cache_val = None

            # Multi-period effective multipliers: 真实倍率(当前/1h/1d/7d) e.g. 0.07/0.07/0.07/--
            eff1h_samples = [h["eff"] for h in hist_items if h.get("eff") is not None and h["t"] >= now - 3600]
            eff1d_samples = [h["eff"] for h in hist_items if h.get("eff") is not None and h["t"] >= now - 86400]
            eff7d_samples = [h["eff"] for h in hist_items if h.get("eff") is not None and h["t"] >= now - 7 * 86400]

            if eff_mult_val is not None:
                cur_eff_num = f"{eff_mult_val:.2f}"
                eff1h_num = cur_eff_num
                eff1d_num = f"{(sum(eff1d_samples) / len(eff1d_samples)):.2f}" if (eff1d_samples and len(eff1d_samples) >= 5 and hist_span >= 7200) else cur_eff_num
                eff7d_num = f"{(sum(eff7d_samples) / len(eff7d_samples)):.2f}" if (eff7d_samples and len(eff7d_samples) >= 10 and hist_span >= 86400 * 3) else "--"
                eff_multi_str = f"{cur_eff_num}/{eff1h_num}/{eff1d_num}/{eff7d_num}"
            elif eff1h_samples:
                eff1h_avg = sum(eff1h_samples) / len(eff1h_samples)
                eff1d_num = f"{(sum(eff1d_samples) / len(eff1d_samples)):.2f}" if (eff1d_samples and hist_span >= 7200) else f"{eff1h_avg:.2f}"
                eff7d_num = f"{(sum(eff7d_samples) / len(eff7d_samples)):.2f}" if (eff7d_samples and hist_span >= 86400 * 3) else "--"
                eff_multi_str = f"--/{eff1h_avg:.2f}/{eff1d_num}/{eff7d_num}"
            else:
                eff_multi_str = "--/--/--/--"

            # Append current reading to metrics history (record any valid metric independently)
            if has_sr or has_cache or eff_mult_val is not None:
                if code not in metrics_history:
                    metrics_history[code] = []
                
                cur_t = int(now)
                rec = {"t": cur_t}
                if eff_mult_val is not None:
                    rec["eff"] = round(eff_mult_val, 4)
                if has_cache:
                    rec["cache"] = round(cache_hit_val, 1)
                if has_sr and sr_percent is not None:
                    rec["sr"] = round(sr_percent, 1)

                if len(rec) > 1:
                    # Update if sample is within 30 seconds to prevent spamming duplicates, else append
                    if metrics_history[code] and abs(metrics_history[code][-1].get("t", 0) - cur_t) < 30:
                        metrics_history[code][-1].update(rec)
                    else:
                        metrics_history[code].append(rec)
                    metrics_history[code] = [h for h in metrics_history[code] if h["t"] >= now - 7 * 86400]

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

            if not is_avail or not visible_in_hall:
                off_reason = f"探针异常: {error_cat}" if error_cat else "官方大厅未在架/离线"
                det_tip += f"\n⚠️ [官网状态]: 当前大厅已下架 ({off_reason})"

            all_parsed_providers.append({
                "code": code,
                "group_id": group_id,
                "rate_multiplier": mult,
                "multiplier_str": f"{mult:.2f}x",
                "effective_multiplier": eff_mult_val,
                "effective_multiplier_str": eff_mult_str,
                "effective_multiplier_ready": eff_ready,
                "effective_multiplier_reason": eff_reason_str,
                "effective_multiplier_multi_str": eff_multi_str,
                "effective_input_price": price_1m,
                "effective_input_price_str": price_1m_str,
                "cache_hit_rate": cache_hit_str,
                "cache_hit_val": cache_hit_val,
                "cache_hit_multi_str": cache_multi_str,
                "reference_cache_hit_rate": ref_cache_str,
                "reference_cache_val": ref_cache_val,
                "has_cache_rate": has_cache,
                "ttft_str": ttft_str,
                "ttft_ms": ttft_ms or 99999,
                "tps_str": tps_str,
                "success_rate": sr_percent,
                "success_rate_str": sr_str,
                "success_rate_multi_str": sr_multi_str,
                "has_success_rate": has_sr,
                "available": is_avail,
                "visible_in_hall": visible_in_hall,
                "error_category": error_cat,
                "is_online": is_avail and visible_in_hall,
                "has_image": bool(img_url),
                "image_url": full_img_url,
                "detection_status": det_status,
                "detection_label": det_label,
                "detection_color": det_color,
                "detection_dot": det_dot,
                "detection_tip": det_tip,
                "detection_model": md_model,
                "detection_raw_status": md_status,
                "public_detail": (it.get("public_detail") or "").strip(),
                "is_excluded": code in excluded_codes,
                "hist_span_hours": round(hist_span / 3600, 1),
            })

        # Persist updated rolling metrics history
        try:
            with open(metrics_history_file, "w", encoding="utf-8") as f:
                json.dump(metrics_history, f, ensure_ascii=False)
        except Exception:
            pass

        # Ensure manually selected providers that might be completely absent from API are still tracked as unlisted
        selected_codes = self.get_selected_providers() or []
        parsed_codes = {p["code"] for p in all_parsed_providers}
        for sel_c in selected_codes:
            if sel_c not in parsed_codes and sel_c not in excluded_codes:
                all_parsed_providers.append({
                    "code": sel_c,
                    "group_id": None,
                    "rate_multiplier": 1.0,
                    "multiplier_str": "--",
                    "effective_multiplier": None,
                    "effective_multiplier_str": "--",
                    "effective_multiplier_ready": False,
                    "effective_multiplier_reason": "官方无此数据",
                    "effective_multiplier_multi_str": "--/--/--/--",
                    "effective_input_price": None,
                    "effective_input_price_str": "--",
                    "cache_hit_rate": "--",
                    "cache_hit_val": 0.0,
                    "cache_hit_multi_str": "--/--/--/--",
                    "reference_cache_hit_rate": "--",
                    "reference_cache_val": None,
                    "has_cache_rate": False,
                    "ttft_str": "--",
                    "ttft_ms": 99999,
                    "tps_str": "--",
                    "success_rate": None,
                    "success_rate_str": "--",
                    "success_rate_multi_str": "--/--/--",
                    "has_success_rate": False,
                    "available": False,
                    "visible_in_hall": False,
                    "error_category": "unlisted",
                    "is_online": False,
                    "has_image": False,
                    "image_url": "",
                    "detection_status": "other",
                    "detection_label": "已下架",
                    "detection_color": "#64748B",
                    "detection_dot": "⚪",
                    "detection_tip": f"供应商: {sel_c}\n⚠️ 当前在官方API大厅已完全下架/无数据",
                    "detection_model": "",
                    "detection_raw_status": None,
                    "public_detail": "官方大厅已下架",
                    "is_excluded": False,
                    "hist_span_hours": 0.0,
                })

        # Sort all providers alphabetically by name for selection dialogs
        all_parsed_providers.sort(key=lambda x: x["code"].lower())

        # Determine monitored rows based on auto/manual mode
        is_auto = self.get_auto_mode()

        if is_auto:
            # Automatic mode: dynamically filter matching default thresholds (updated every minute)
            # 严格筛选：必须当前在架并可用 (available=True 且 visible_in_hall=True)，具备实测有效缓存率与成功率（>= 80%）
            matched_providers = [
                p for p in all_parsed_providers
                if p["code"] not in excluded_codes
                and p["available"]
                and p.get("visible_in_hall", True)
                and p["has_success_rate"]
                and p["success_rate"] is not None
                and p["success_rate"] >= DEFAULT_FILTER_MIN_SR
                and p["has_cache_rate"]
                and p["cache_hit_val"] >= DEFAULT_FILTER_MIN_CACHE
                and p["effective_multiplier"] is not None
                and p["effective_multiplier"] <= DEFAULT_FILTER_MAX_EFF
                and p["rate_multiplier"] <= DEFAULT_FILTER_MAX_NOM
            ]
            if matched_providers:
                monitored_rows = matched_providers
            else:
                # Fallback: strictly require valid cache, success rate, and online status
                monitored_rows = [
                    p for p in all_parsed_providers
                    if p["code"] not in excluded_codes
                    and p["available"]
                    and p.get("visible_in_hall", True)
                    and p["has_success_rate"]
                    and p["success_rate"] is not None
                    and p["success_rate"] >= DEFAULT_FILTER_MIN_SR
                    and p["has_cache_rate"]
                    and p["cache_hit_val"] >= DEFAULT_FILTER_MIN_CACHE
                ][:5]
                if not monitored_rows:
                    monitored_rows = []
        else:
            # Manual mode: use user's checked providers
            monitored_rows = [p for p in all_parsed_providers if p["code"] in selected_codes and p["code"] not in excluded_codes]
            if not monitored_rows:
                monitored_rows = [
                    p for p in all_parsed_providers
                    if p["code"] not in excluded_codes
                    and p["has_success_rate"]
                    and p["has_cache_rate"]
                ][:5]

        # Always sort monitored rows by effective multiplier ascending, placing unmeasured/None at the end
        monitored_rows.sort(
            key=lambda x: (
                x["effective_multiplier"] is None,
                x["effective_multiplier"] if x["effective_multiplier"] is not None else 999.0,
                x["rate_multiplier"]
            )
        )

        result = {
            "success": True,
            "auto_mode": is_auto,
            "all_providers": all_parsed_providers,
            "monitored_providers": monitored_rows,
            "top_groups": monitored_rows,
            "selected_codes": selected_codes,
            "excluded_codes": list(excluded_codes),
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
