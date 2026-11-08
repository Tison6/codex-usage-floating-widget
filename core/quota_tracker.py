"""
ChatGPT / Codex Quota History Tracker and Burn-Rate Predictor.
Persists quota timeline, calculates 7-day ideal baseline (副对角线基准),
computes burn rate and predicts exact quota exhaustion time.
Includes exact minute-level timestamps (MM-DD HH:MM).
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


def format_duration_compact(seconds: int) -> str:
    """Format duration into clean compact units (e.g. 1d18h, 3h7m)."""
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
    if minutes > 0 and days == 0:  # If less than 1 day, show minutes
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{minutes}m" if minutes > 0 else "<1m")
        
    return "".join(parts)


class QuotaTracker:
    """Manages history persistence and analytical trend metrics."""
    
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.history_file = os.path.join(data_dir, "quota_history.json")
        self.history: List[Dict[str, Any]] = self._load_history()

    def _load_history(self) -> List[Dict[str, Any]]:
        """Load historical points from disk."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self):
        """Save history points to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[QuotaTracker] Save history failed: {e}")

    def record_snapshot(self, codex_data: Dict[str, Any]):
        """Record a single usage snapshot."""
        if not codex_data.get("success"):
            return
        
        w = codex_data.get("weekly_window") or codex_data.get("primary_window")
        if not w:
            return
            
        now = int(time.time())
        used = w.get("used_percent", 0)
        remain = w.get("remaining_percent", 100)
        reset_at = w.get("reset_at")
        if not reset_at:
            reset_after = w.get("reset_after_seconds", 0)
            reset_at = now + reset_after
            
        five_h = codex_data.get("five_hour_window")
        fh_used = five_h.get("used_percent") if five_h else None
        fh_remain = five_h.get("remaining_percent") if five_h else None
        fh_reset_at = five_h.get("reset_at") if five_h else None
        if five_h and not fh_reset_at:
            fh_reset_after = five_h.get("reset_after_seconds", 0)
            fh_reset_at = now + fh_reset_after
            
        if self.history:
            last = self.history[-1]
            if (last.get("reset_at") == reset_at and 
                last.get("remaining_percent") == remain and 
                last.get("fh_remaining_percent") == fh_remain and 
                (now - last.get("timestamp", 0) < 180)):
                return
                
        self.history.append({
            "timestamp": now,
            "used_percent": used,
            "remaining_percent": remain,
            "reset_at": reset_at,
            "fh_used_percent": fh_used,
            "fh_remaining_percent": fh_remain,
            "fh_reset_at": fh_reset_at,
            "plan_type": codex_data.get("plan_type", "PLUS")
        })
        
        cutoff = now - (30 * 86400)
        self.history = [h for h in self.history if h.get("timestamp", 0) >= cutoff]
        self._save_history()

    def get_analysis_for_current_cycle(self, w: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Compute 7-day cycle coordinates, ideal burn-line, actual curve points,
        and estimated exhaustion time down to the exact minute (MM-DD HH:MM).
        """
        now = int(time.time())
        
        if not w and self.history:
            last = self.history[-1]
            reset_at = last.get("reset_at", now + 604800)
            current_remain = last.get("remaining_percent", 100)
            window_seconds = 604800
        elif w:
            reset_after = w.get("reset_after_seconds", 604800)
            reset_at = w.get("reset_at") or (now + reset_after)
            current_remain = w.get("remaining_percent", 100)
            window_seconds = w.get("window_seconds", 604800)
        else:
            return {
                "has_data": False,
                "current_remain": 100,
                "ideal_remain": 100,
                "pace_status": "未知",
                "exhaustion_text": "暂无数据",
                "curve_points": [],
                "cycle_progress": 0.0
            }

        cycle_start = reset_at - window_seconds
        cycle_end = reset_at
        
        is_short_window = (window_seconds <= 86400)
        if is_short_window:
            cycle_points = [
                {"timestamp": p["timestamp"], "remaining_percent": p["fh_remaining_percent"]}
                for p in self.history
                if p.get("fh_reset_at") == reset_at and p.get("fh_remaining_percent") is not None and cycle_start <= p.get("timestamp", 0) <= cycle_end
            ]
        else:
            cycle_points = [
                p for p in self.history
                if p.get("reset_at") == reset_at and cycle_start <= p.get("timestamp", 0) <= cycle_end
            ]
        
        normalized_points: List[Tuple[float, float]] = []
        normalized_points.append((0.0, 100.0))
        
        for p in cycle_points:
            t = p.get("timestamp", now)
            t_norm = max(0.0, min(1.0, (t - cycle_start) / float(window_seconds)))
            r_val = float(p.get("remaining_percent", 100.0))
            normalized_points.append((t_norm, r_val))
            
        now_norm = max(0.0, min(1.0, (now - cycle_start) / float(window_seconds)))
        if not normalized_points or normalized_points[-1][0] < now_norm:
            normalized_points.append((now_norm, float(current_remain)))
            
        normalized_points.sort(key=lambda x: x[0])
        
        ideal_remain = max(0.0, 100.0 * (1.0 - now_norm))
        
        min_elapsed = 180 if is_short_window else 1800
        elapsed_secs = max(min_elapsed, now - cycle_start)
        used_total = 100.0 - float(current_remain)
        burn_rate_per_hour = (used_total / elapsed_secs) * 3600.0
        
        if float(current_remain) <= 0:
            exhaustion_text = "额度已耗尽: 等待重置"
            pace_status = "已耗尽"
        elif burn_rate_per_hour > 0.01:
            hours_to_zero = float(current_remain) / burn_rate_per_hour
            secs_to_zero = int(hours_to_zero * 3600)
            exhaust_ts = now + secs_to_zero
            
            dt_exhaust = datetime.fromtimestamp(exhaust_ts)
            exhaust_date_str = dt_exhaust.strftime("%m-%d %H:%M")
            dur_str = format_duration_compact(secs_to_zero)
            
            if exhaust_ts < reset_at:
                exhaustion_text = f"预计耗尽: {dur_str} ({exhaust_date_str})"
                pace_status = "消耗偏快"
            else:
                end_surplus = max(0, int(100.0 - (burn_rate_per_hour * (window_seconds / 3600.0))))
                exhaustion_text = f"速率稳定: 周期末余 ~{end_surplus}%"
                pace_status = "良好"
        else:
            exhaustion_text = "消耗极低: 可用至重置"
            pace_status = "充足"

        diff_from_ideal = float(current_remain) - ideal_remain
        
        return {
            "has_data": True,
            "current_remain": current_remain,
            "ideal_remain": round(ideal_remain, 1),
            "diff_from_ideal": round(diff_from_ideal, 1),
            "burn_rate_per_day": round(burn_rate_per_hour * 24.0, 1),
            "pace_status": pace_status,
            "pace_color": "#9CA3AF",
            "exhaustion_text": exhaustion_text,
            "cycle_progress": now_norm,
            "curve_points": normalized_points,
        }
