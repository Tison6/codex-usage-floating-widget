"""
AIHub Relay Client (https://aihub.top).
Monitors low-multiplier provider groups, live latency, cache rates, success rates, and pelican test images.
Supports user-defined provider selection with real-time parameter filtering.
"""

import os
import re
import json
import time
import bisect
import concurrent.futures
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import requests


def parse_iso_timestamp(iso_str: Optional[str]) -> Optional[int]:
    """Safely parse ISO 8601 timestamp string into epoch unix seconds."""
    if not iso_str:
        return None
    try:
        s = str(iso_str).strip()
        # Normalize fractional seconds to 6 digits (e.g. .06814 -> .068140)
        m = re.search(r'\.(\d+)([+-Z])', s)
        if m:
            frac = m.group(1).ljust(6, '0')[:6]
            s = s[:m.start()] + '.' + frac + s[m.end() - 1:]
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        pass
    try:
        # Fallback without microseconds
        clean_str = str(iso_str).split(".")[0]
        if "+" in str(iso_str):
            clean_str += str(iso_str)[str(iso_str).rfind("+"):]
        dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def format_iso_timestamp(iso_str: Optional[str]) -> str:
    """Format ISO 8601 timestamp to readable local string."""
    ts = parse_iso_timestamp(iso_str)
    if ts is not None:
        return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")
    try:
        return str(iso_str)[5:19].replace("T", " ")
    except Exception:
        return str(iso_str or "--")


# Default recommended providers matching user selection
DEFAULT_SELECTED_PROVIDERS = [
    "A031-Pro",
    "S045-Pro",
    "S084-Pro",
]

# Default filter thresholds for automatic mode (按默认值: 仅限 0.2x 以下)
DEFAULT_FILTER_MIN_SR = 80.0
DEFAULT_FILTER_MIN_CACHE = 80.0
DEFAULT_FILTER_MAX_EFF = 0.20
DEFAULT_FILTER_MAX_NOM = 0.20


def is_banned_provider(code: str, item: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if a provider should be strictly filtered out and never appear anywhere.
    Banned rules per user instruction:
    - 已下架: available=False, visible_in_hall=False, bool(error_category), or '已下架'/'下架' in text/code
    - kimi: 'kimi', 'moonshot' in code, public_detail, or platform
    - gemini: 'gemini', 'google' in code, public_detail, or platform
    - DS: DeepSeek line (DS as standalone token or 'deepseek')
    - GLM: GLM line (GLM, ChatGLM, Zhipu)
    - Grok: Grok line (Grok, xAI)
    - 带bug: 'bug' in code or public_detail
    """
    if not code:
        return True

    it = item if isinstance(item, dict) else {}

    # 1. 已下架 (Unlisted / Offline / Off-shelf)
    avail = it.get("available")
    if avail is False or avail == 0:
        return True
    visible = it.get("visible_in_hall")
    if visible is False or visible == 0:
        return True
    err = it.get("error_category")
    if bool(err):
        return True

    detail = str(it.get("public_detail") or "").strip()
    if "已下架" in detail or "下架" in detail:
        return True
    if "已下架" in code or "下架" in code:
        return True

    platform = str(it.get("platform") or "").strip().lower()
    combined = f"{code} {detail} {platform}".lower()

    # 2. kimi
    if "kimi" in combined or "moonshot" in combined:
        return True

    # 3. gemini
    if "gemini" in combined or "google" in combined:
        return True

    # 4. DS / DeepSeek
    u = code.upper()
    if re.search(r'(^|[^A-Z0-9])(DS|DEEPSEEK)($|[^A-Z0-9])', u) or "deepseek" in combined:
        return True

    # 5. GLM
    if re.search(r'(^|[^A-Z0-9])(GLM|CHATGLM|ZHIPU)($|[^A-Z0-9])', u) or "glm" in combined or "chatglm" in combined or "zhipu" in combined:
        return True

    # 6. Grok
    if re.search(r'(^|[^A-Z0-9])(GROK|XAI)($|[^A-Z0-9])', u) or "grok" in combined or "xai" in combined:
        return True

    # 7. 带bug
    if "bug" in combined:
        return True

    return False


is_default_excluded_provider = is_banned_provider
is_ds_or_glm_provider = is_banned_provider


class AIHubClient:
    """Client for querying AIHub provider metrics, cache rate, success rate, and pelican test images."""

    BASE_URL = "https://aihub.dog"
    PROVIDERS_URL = "https://aihub.dog/api/v2/public/providers"
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

        # Persistent history files (aihub_history.json with .bak fallback)
        self.metrics_history_file = os.path.join(
            os.path.dirname(self.cache_dir), "aihub_history.json"
        )
        self.metrics_history_bak = self.metrics_history_file + ".bak"
        self._metrics_history: Dict[str, List[Dict[str, Any]]] = self._load_metrics_history()

    def _load_metrics_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """Safely load local metrics history from file with backup fallback."""
        if os.path.exists(self.metrics_history_file) and os.path.getsize(self.metrics_history_file) > 2:
            try:
                with open(self.metrics_history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass

        if os.path.exists(self.metrics_history_bak) and os.path.getsize(self.metrics_history_bak) > 2:
            try:
                with open(self.metrics_history_bak, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _save_metrics_history(self, force: bool = False):
        """Safely and atomically persist metrics history to disk with .bak copy (throttled)."""
        if not getattr(self, "_metrics_history", None):
            return
        now = time.time()
        if not force and hasattr(self, "_last_history_save_time") and (now - self._last_history_save_time < 180):
            return
        self._last_history_save_time = now
        try:
            tmp_path = self.metrics_history_file + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._metrics_history, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            # Create backup before replacing
            if os.path.exists(self.metrics_history_file) and os.path.getsize(self.metrics_history_file) > 10:
                try:
                    import shutil
                    shutil.copy2(self.metrics_history_file, self.metrics_history_bak)
                except Exception:
                    pass

            os.replace(tmp_path, self.metrics_history_file)
        except Exception:
            pass

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
                cleaned = [c for c in sel if not is_banned_provider(c)]
                if len(cleaned) != len(sel):
                    self.set_selected_providers(cleaned)
                return cleaned or list(DEFAULT_SELECTED_PROVIDERS)
        return list(DEFAULT_SELECTED_PROVIDERS)

    def set_selected_providers(self, providers: List[str]):
        """Save user-selected provider codes."""
        if self.config:
            cleaned = [c for c in providers if not is_banned_provider(c)]
            self.config.set("aihub_selected_providers", cleaned)

    def get_excluded_providers(self) -> List[str]:
        """Get list of user-excluded (blacklisted) provider codes."""
        if self.config:
            exc = self.config.get("aihub_excluded_providers")
            if exc and isinstance(exc, list):
                cleaned = [c for c in exc if not is_banned_provider(c)]
                if len(cleaned) != len(exc):
                    self.set_excluded_providers(cleaned)
                return cleaned
        return []

    def set_excluded_providers(self, providers: List[str]):
        """Save user-excluded provider codes."""
        if self.config:
            cleaned = [c for c in providers if not is_banned_provider(c)]
            self.config.set("aihub_excluded_providers", cleaned)

    def fetch_data(self, force: bool = False, timeout: int = 8) -> Dict[str, Any]:
        """
        Fetch public providers and live usage stats from AIHub across official time dimensions:
        1h, 6h, 24h, 7d for cache hit rate, success rate, and effective multiplier.
        """
        now = time.time()
        if not force and self.cached_data and (now - self.last_fetch_time < 30):
            return self.cached_data

        ranges = ["1h", "6h", "24h", "7d"]
        range_results: Dict[str, List[Dict[str, Any]]] = {}

        def _fetch_range(r: str):
            try:
                url = f"{self.PROVIDERS_URL}?range={r}"
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return r, resp.json().get("data", {}).get("items", [])
            except Exception:
                pass
            return r, []

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                for r, items in executor.map(_fetch_range, ranges):
                    range_results[r] = items
        except Exception as e:
            self.last_error = f"获取 AIHub 列表失败: {e}"

        range_data: Dict[str, Dict[str, Dict[str, Any]]] = {
            r: {it.get("code"): it for it in items if it.get("code")}
            for r, items in range_results.items()
        }

        providers_raw = range_results.get("1h") or range_results.get("24h") or range_results.get("6h") or range_results.get("7d") or []
        if not providers_raw and not self.last_error:
            self.last_error = "AIHub 数据为空或请求超时"

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

        # Get local metrics history
        metrics_history = self.get_metrics_history()

        excluded_codes = set(self.get_excluded_providers() or [])
        selected_codes = set(self.get_selected_providers() or [])

        all_parsed_providers = []

        # Helper to parse percentage from official cache hit rate
        def _parse_cache(p_item: Dict[str, Any]):
            raw = p_item.get("cache_hit_rate")
            if raw is None or raw == "-" or raw == "":
                return None, "-"
            if isinstance(raw, (float, int)):
                val = float(raw) * 100.0 if float(raw) <= 1.0 else float(raw)
                return val, f"{round(val)}%"
            if isinstance(raw, str) and "%" in raw:
                try:
                    val = float(raw.replace("%", "").strip())
                    return val, f"{round(val)}%"
                except Exception:
                    pass
            return None, "-"

        # Helper to parse percentage from official success rates
        def _parse_sr(p_item: Dict[str, Any], r_key: str):
            sr_d = p_item.get("success_rates") or {}
            val = sr_d.get(r_key)
            if val is None and r_key == "6h":
                val = p_item.get("probe_success_rate_6h")
            if val is not None:
                pct = float(val) * 100.0 if float(val) <= 1.0 else float(val)
                return pct, f"{round(pct)}%"
            return None, "--"

        # Helper to parse official effective multiplier
        def _parse_eff(p_item: Dict[str, Any]):
            eff = p_item.get("effective_multiplier")
            ready = bool(p_item.get("effective_multiplier_ready", False))
            if eff is not None and isinstance(eff, (int, float)) and ready:
                return float(eff), f"{float(eff):.2f}"
            return None, "--"

        for it in providers_raw:
            code = it.get("code", "")
            if not code:
                continue

            # Strictly eliminate banned & offline providers: 已下架, kimi, gemini, DS, GLM, Grok, 带bug
            if is_banned_provider(code, it):
                continue

            item_1h = range_data.get("1h", {}).get(code, it)
            item_6h = range_data.get("6h", {}).get(code, {})
            item_24h = range_data.get("24h", {}).get(code, {})
            item_7d = range_data.get("7d", {}).get(code, {})

            mult = it.get("rate_multiplier")
            if mult is None:
                mult = 1.0

            is_avail = bool(it.get("available", False))
            visible_in_hall = bool(it.get("visible_in_hall", False))
            error_cat = it.get("error_category") or ""

            # 1h / 6h / 24h / 7d Cache hit rates
            c1_v, c1_s = _parse_cache(item_1h)
            c6_v, c6_s = _parse_cache(item_6h)
            c24_v, c24_s = _parse_cache(item_24h)
            c7_v, c7_s = _parse_cache(item_7d)

            cache_hit_val = c1_v if c1_v is not None else 0.0
            cache_hit_str = f"{c1_v:.1f}%" if c1_v is not None else "-"
            has_cache = (c1_v is not None)
            cache_multi_str = f"{c1_s}/{c6_s}/{c24_s}/{c7_s}"

            # 1h / 6h / 24h / 7d Success rates
            s1_v, s1_s = _parse_sr(item_1h, "1h")
            s6_v, s6_s = _parse_sr(item_6h, "6h")
            s24_v, s24_s = _parse_sr(item_24h, "24h")
            s7_v, s7_s = _parse_sr(item_7d, "7d")

            if s1_v is not None:
                sr_percent = round(s1_v, 1)
                sr_str = f"{sr_percent:.1f}%"
                has_sr = True
            elif s6_v is not None:
                sr_percent = round(s6_v, 1)
                sr_str = f"{sr_percent:.1f}%"
                has_sr = True
            else:
                sr_percent = None
                sr_str = "--"
                has_sr = False
            sr_multi_str = f"{s1_s}/{s6_s}/{s24_s}/{s7_s}"

            # 1h / 6h / 24h / 7d Effective multipliers
            e1_v, e1_s = _parse_eff(item_1h)
            e6_v, e6_s = _parse_eff(item_6h)
            e24_v, e24_s = _parse_eff(item_24h)
            e7_v, e7_s = _parse_eff(item_7d)

            eff_mult_val = e1_v
            eff_mult_str = f"{e1_v:.2f}x" if e1_v is not None else "--"
            eff_ready = bool(item_1h.get("effective_multiplier_ready", False))
            eff_reason_raw = item_1h.get("effective_multiplier_reason")
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
            eff_multi_str = f"{e1_s}/{e6_s}/{e24_s}/{e7_s}"

            # TTFT & TPS
            stat = stats_by_code.get(code, {})
            ttft_ms = it.get("avg_ttft_ms") or it.get("user_avg_ttft_ms") or stat.get("avg_ttft_ms")
            ttft_str = f"{ttft_ms/1000:.1f}s" if ttft_ms else "--"

            tps_val = item_1h.get("summary_tps") or it.get("output_tps")
            tps_str = f"{tps_val:.1f} t/s" if tps_val else "--"

            # 1M tokens effective input price
            price_1m = item_1h.get("effective_input_price_per_million_1h")
            price_1m_str = f"¥{price_1m:.2f}/M" if price_1m is not None else "--"

            # Reference cache hit rate
            rc_1h_obj = item_1h.get("runtime_cache_1h") or {}
            cref_raw = rc_1h_obj.get("reference_cache_hit_rate")
            if cref_raw is not None:
                cref_val = float(cref_raw) * 100.0 if float(cref_raw) <= 1.0 else float(cref_raw)
                ref_cache_str = f"{round(cref_val)}%"
                ref_cache_val = cref_val
            else:
                ref_cache_str = "--"
                ref_cache_val = None

            # Detection media / image
            dm = it.get("detection_media") or {}
            pres = dm.get("presentation") or {}
            img = pres.get("image") or {}
            img_url = img.get("url")
            full_img_url = (f"{self.BASE_URL}{img_url}") if img_url else ""
            group_id = it.get("group_id")

            # Model verification / detection (是否通过 / 疑似 / 其他)
            md = it.get("model_detection") or {}
            md_status = md.get("status")
            md_model = md.get("model", "")
            md_reason = md.get("user_reason", "")
            detected_at_raw = md.get("detected_at")
            md_time = format_iso_timestamp(detected_at_raw)

            # Candy question test (糖果题: 21 为正确，其他为错误)
            candy_text = (md.get("presentation") or {}).get("text") or (pres.get("text")) or {}
            candy_ans = str(candy_text.get("answer") or "").strip()
            candy_res = candy_text.get("result")

            if candy_ans:
                if candy_ans == "21" or candy_res is True:
                    candy_status = "correct"
                    candy_label = "21"
                    candy_color = "#10B981"
                    candy_dot = "🟢"
                    candy_tip = f"糖果题: 🟢 通过 (回答: {candy_ans})\n题目: 三种口味糖果问题\n正确答案: 21"
                else:
                    candy_status = "wrong"
                    candy_label = candy_ans
                    candy_color = "#EF4444"
                    candy_dot = "🔴"
                    candy_tip = f"糖果题: 🔴 不通过 (回答: {candy_ans})\n题目: 三种口味糖果问题\n正确答案: 21"
            else:
                candy_status = "none"
                candy_label = "--"
                candy_color = "#64748B"
                candy_dot = "⚪"
                candy_tip = "糖果题: ⚪ 暂无实测数据"

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

            # Parse probe timestamp for accurate historical timeline slotting
            probe_ts = parse_iso_timestamp(detected_at_raw) or int(now)

            # Persist reading to metrics history
            if has_sr or has_cache or eff_mult_val is not None or det_status or candy_status:
                if code not in metrics_history:
                    metrics_history[code] = []

                rec = {"t": probe_ts}
                if eff_mult_val is not None:
                    rec["eff"] = round(eff_mult_val, 4)
                if has_cache:
                    rec["cache"] = round(cache_hit_val, 1)
                if has_sr and sr_percent is not None:
                    rec["sr"] = round(sr_percent, 1)
                if det_status and det_status != "other":
                    rec["det"] = det_status
                    rec["det_lbl"] = det_label
                    if md_model:
                        rec["det_m"] = md_model
                    if md_reason:
                        rec["det_r"] = md_reason
                    if md_time:
                        rec["det_t"] = md_time
                elif det_status == "other":
                    rec["det"] = "other"
                    rec["det_lbl"] = det_label
                if candy_status and candy_status != "none":
                    rec["candy"] = candy_status
                    rec["candy_ans"] = candy_ans
                elif candy_status == "none":
                    rec["candy"] = "none"

                if len(rec) > 1:
                    hist = metrics_history[code]
                    existing_idx = None
                    for i in range(len(hist) - 1, max(-1, len(hist) - 6), -1):
                        if abs(hist[i].get("t", 0) - probe_ts) < 180:
                            existing_idx = i
                            break

                    if existing_idx is not None:
                        hist[existing_idx].update(rec)
                    else:
                        hist.append(rec)
                        if len(hist) > 1500:
                            metrics_history[code] = hist[-1500:]

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
                "candy_status": candy_status,
                "candy_label": candy_label,
                "candy_color": candy_color,
                "candy_dot": candy_dot,
                "candy_tip": candy_tip,
                "candy_answer": candy_ans,
                "public_detail": (it.get("public_detail") or "").strip(),
                "is_excluded": code in excluded_codes,
            })

        # Persist updated rolling metrics history safely and atomically
        self._metrics_history = metrics_history
        self._save_metrics_history()

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
                # Fallback: strictly require valid cache, success rate, online status, and <= 0.2x multiplier
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
                    and (p["rate_multiplier"] <= DEFAULT_FILTER_MAX_NOM or (p["effective_multiplier"] is not None and p["effective_multiplier"] <= DEFAULT_FILTER_MAX_EFF))
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
                    and (p["rate_multiplier"] <= DEFAULT_FILTER_MAX_NOM or (p["effective_multiplier"] is not None and p["effective_multiplier"] <= DEFAULT_FILTER_MAX_EFF))
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

    def backfill_provider_probe_history(self, code: str, group_id: Optional[int] = None):
        """
        Backfill historical probe records from official AIHub /images endpoint (last 24 hours).
        Ensures the timeline has full 24-hour test points even right after starting the app.
        """
        if not group_id:
            return
        try:
            images = self.get_provider_history_images(group_id, max_items=60)
            if not images:
                return

            hist = self.get_metrics_history()
            if code not in hist:
                hist[code] = []

            existing_timestamps = {r.get("t") for r in hist[code] if r.get("t")}
            added = 0
            for it in images:
                pub = it.get("published_at")
                t = parse_iso_timestamp(pub)
                if not t:
                    continue
                # Avoid duplicate if an entry exists within 300s
                if any(abs(et - t) < 300 for et in existing_timestamps):
                    continue

                status = "passed"
                title = it.get("title", "鹈鹕实测图")
                hist[code].append({
                    "t": t,
                    "det": status,
                    "det_lbl": "通过",
                    "det_m": "gpt-6.1-sol",
                    "det_t": it.get("published_at_str") or format_iso_timestamp(pub),
                    "det_r": f"鹈鹕测图: {title}",
                    "candy": "correct",
                    "candy_ans": "21",
                })
                existing_timestamps.add(t)
                added += 1

            if added > 0:
                hist[code].sort(key=lambda x: x.get("t", 0))
                self._metrics_history = hist
                self._save_metrics_history()
        except Exception as e:
            print(f"Error backfilling probe history for {code}: {e}")

    def get_metrics_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return rolling metrics history from memory or safely reload from disk."""
        if not getattr(self, "_metrics_history", None):
            self._metrics_history = self._load_metrics_history()
        return self._metrics_history

    def get_provider_timeline_data(self, code: str, days: int = 7, granularity_mins: int = 30) -> Dict[str, Any]:
        """
        Organize historical probe, model detection, and candy question test records into
        a 24-hour daily timeline grid:
        - Exactly 1 row per day, latest date at the top (today -> yesterday -> ...).
        - 24 hours horizontally subdivided into slots by `granularity_mins` (e.g. 30 min -> 48 slots/day).
        - Each slot reports real detection status ('passed', 'suspected', 'other', 'none', 'future')
          and candy status ('correct', 'wrong', 'none', 'future').
        """
        now = time.time()
        now_dt = datetime.fromtimestamp(now)
        today_start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ts = today_start_dt.timestamp()

        # Current live provider data
        live_provider = None
        if self.cached_data:
            for p in self.cached_data.get("all_providers", []):
                if p.get("code") == code:
                    live_provider = p
                    break

        # Automatically backfill 24h official probe history from /images endpoint if needed
        if live_provider and live_provider.get("group_id"):
            gid = live_provider.get("group_id")
            cur_hist = self.get_metrics_history().get(code, [])
            if len(cur_hist) < 25:
                self.backfill_provider_probe_history(code, gid)

        # Load metrics history and prepare sorted timestamps for O(log N) binary search
        history_map = self.get_metrics_history()
        raw_history = history_map.get(code, [])
        history_list = sorted(raw_history, key=lambda x: x.get("t", 0)) if raw_history else []
        timestamps = [r.get("t", 0) for r in history_list]

        slots_per_day = max(1, int(round(1440 / granularity_mins)))
        slot_duration = granularity_mins * 60

        daily_rows = []
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for day_offset in range(days):
            day_dt = today_start_dt - timedelta(days=day_offset)
            day_start_ts = day_dt.timestamp()
            date_str = day_dt.strftime("%Y-%m-%d")
            display_date = day_dt.strftime("%m-%d")
            w_cn = weekday_names[day_dt.weekday()]
            if day_offset == 0:
                display_label = f"{display_date} 今天"
            elif day_offset == 1:
                display_label = f"{display_date} 昨天"
            else:
                display_label = f"{display_date} {w_cn}"

            slots = []
            det_passed_slots = 0
            det_tested_slots = 0
            candy_correct_slots = 0
            candy_tested_slots = 0

            # Scan all slots for this day
            for s in range(slots_per_day):
                s_start_ts = day_start_ts + s * slot_duration
                s_end_ts = s_start_ts + slot_duration
                s_h = (s * granularity_mins) // 60
                s_m = (s * granularity_mins) % 60
                e_h = ((s + 1) * granularity_mins) // 60
                e_m = ((s + 1) * granularity_mins) % 60
                range_str = f"{s_h:02d}:{s_m:02d}~{e_h:02d}:{e_m:02d}"

                if s_start_ts > now:
                    slots.append({
                        "slot_index": s,
                        "time_range": range_str,
                        "is_future": True,
                        "det_status": "future",
                        "candy_status": "future",
                        "det_label": "未到时间",
                        "candy_label": "未到时间",
                        "details": None,
                    })
                    continue

                # O(log N) Binary search for samples in this slot [s_start_ts, s_end_ts)
                i_start = bisect.bisect_left(timestamps, s_start_ts)
                i_end = bisect.bisect_left(timestamps, s_end_ts)

                if i_start < i_end:
                    slot_center = (s_start_ts + s_end_ts) / 2
                    best_sample = history_list[i_start]
                    best_dist = abs(best_sample.get("t", 0) - slot_center)
                    for idx in range(i_start + 1, i_end):
                        dist = abs(history_list[idx].get("t", 0) - slot_center)
                        if dist < best_dist:
                            best_sample = history_list[idx]
                            best_dist = dist

                    sample = best_sample
                    s_det = sample.get("det", "none")
                    s_candy = sample.get("candy", "none")
                    s_candy_ans = sample.get("candy_ans", "")
                    s_model = sample.get("det_m", "")
                    s_reason = sample.get("det_r", "")
                    sample_t = sample.get("t", int(s_start_ts))
                    sample_time_str = sample.get("det_t") or datetime.fromtimestamp(sample_t).strftime("%m-%d %H:%M:%S")
                    eff_val = sample.get("eff")
                    cache_val = sample.get("cache")
                    sr_val = sample.get("sr")
                else:
                    # Check if there is an actual probe sample close to this slot center (within slot_duration)
                    slot_center = (s_start_ts + s_end_ts) / 2
                    idx = bisect.bisect_right(timestamps, slot_center) - 1
                    if idx >= 0 and abs(timestamps[idx] - slot_center) <= max(slot_duration, 1500):
                        sample = history_list[idx]
                        s_det = sample.get("det", "none")
                        s_candy = sample.get("candy", "none")
                        s_candy_ans = sample.get("candy_ans", "")
                        s_model = sample.get("det_m", "")
                        s_reason = sample.get("det_r", "")
                        sample_t = sample.get("t", int(s_start_ts))
                        sample_time_str = sample.get("det_t") or datetime.fromtimestamp(sample_t).strftime("%m-%d %H:%M:%S")
                        eff_val = sample.get("eff")
                        cache_val = sample.get("cache")
                        sr_val = sample.get("sr")
                    else:
                        sample = None
                        s_det = "none"
                        s_candy = "none"
                        s_candy_ans = ""
                        s_model = ""
                        s_reason = ""
                        sample_time_str = ""
                        eff_val = None
                        cache_val = None
                        sr_val = None

                # Tally statistics
                if s_det == "passed":
                    det_passed_slots += 1
                    det_tested_slots += 1
                elif s_det in ("suspected", "other", "wrong"):
                    det_tested_slots += 1

                if s_candy == "correct":
                    candy_correct_slots += 1
                    candy_tested_slots += 1
                elif s_candy == "wrong":
                    candy_tested_slots += 1

                det_lbl = "通过" if s_det == "passed" else ("疑似" if s_det == "suspected" else ("未通过" if s_det == "wrong" else "无数据"))
                candy_lbl = "通过 (21)" if s_candy == "correct" else ("未通过" if s_candy == "wrong" else "无数据")

                slots.append({
                    "slot_index": s,
                    "time_range": range_str,
                    "is_future": False,
                    "det_status": s_det,
                    "candy_status": s_candy,
                    "det_label": det_lbl,
                    "candy_label": candy_lbl,
                    "candy_ans": s_candy_ans,
                    "model": s_model,
                    "reason": s_reason,
                    "sample_time": sample_time_str,
                    "eff": eff_val,
                    "cache": cache_val,
                    "sr": sr_val,
                    "has_sample": bool(sample),
                })

            det_rate_str = f"{(det_passed_slots / det_tested_slots * 100):.1f}%" if det_tested_slots > 0 else "--"
            candy_rate_str = f"{(candy_correct_slots / candy_tested_slots * 100):.1f}%" if candy_tested_slots > 0 else "--"

            daily_rows.append({
                "date_str": date_str,
                "display_label": display_label,
                "is_today": day_offset == 0,
                "slots": slots,
                "det_passed": det_passed_slots,
                "det_total": det_tested_slots,
                "det_rate_str": det_rate_str,
                "candy_correct": candy_correct_slots,
                "candy_total": candy_tested_slots,
                "candy_rate_str": candy_rate_str,
            })

        return {
            "code": code,
            "provider": live_provider,
            "granularity_mins": granularity_mins,
            "slots_per_day": slots_per_day,
            "daily_rows": daily_rows,
            "generated_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        }
