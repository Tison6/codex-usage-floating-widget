"""
Compact ChatGPT / Codex View Component with 5H & Weekly Rate Limits, Grid Sparkline & Status Light.
Only shows remaining percentage, exact minute timestamps (MM-DD HH:MM),
uniform subtext font size, and dynamic status light.
Supports dynamic proportional font and dimension scaling.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.sparkline_widget import QuotaSparklineWidget
from ui.status_light import CodexStatusLight
from ui.icons import get_openai_pixmap, get_claude_pixmap
from core.quota_tracker import QuotaTracker


class CodexQuotaView(QWidget):
    """Compact view for ChatGPT Plus / Codex usage stats & 7-Day Burn Sparkline."""
    
    refresh_requested = pyqtSignal()
    
    def __init__(self, quota_tracker: QuotaTracker, parent=None, scale: float = 1.0, provider: str = "ChatGPT"):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.provider = provider
        self.text_color = "#E5E7EB"
        self.subtext_color = "#9CA3AF"
        self._logo_pixmap = get_claude_pixmap if provider == "Claude" else get_openai_pixmap
        self.tracker = quota_tracker
        self.scale = max(0.5, float(scale))
        self._last_data: Dict[str, Any] = {}
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)
        
        # Header
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(2, 0, 2, 0)
        self.header_layout.setSpacing(5)
        
        logo_sz = max(9, int(round(13 * self.scale)))
        self.logo_lbl = QLabel(self)
        self.logo_lbl.setPixmap(self._logo_pixmap(logo_sz))
        
        self.title_lbl = QLabel(provider, self)
        self.title_lbl.setProperty("class", "SectionHeader")
        
        self.plan_badge = QLabel("--", self)
        self.plan_badge.setProperty("class", "BadgePlan")
        
        btn_sz = max(14, int(round(18 * self.scale)))
        self.refresh_btn = QPushButton("🔄", self)
        self.refresh_btn.setProperty("class", "IconButton")
        self.refresh_btn.setFixedSize(btn_sz, btn_sz)
        self.refresh_btn.setToolTip(f"点击立即刷新 {provider} 用量")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        self.header_layout.addWidget(self.logo_lbl)
        self.header_layout.addWidget(self.title_lbl)
        self.header_layout.addWidget(self.plan_badge)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.refresh_btn)
        
        self.main_layout.addLayout(self.header_layout)
        
        # Card Container
        self.card = QFrame(self)
        self.card.setProperty("class", "CardSection")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(8, 6, 8, 6)
        self.card_layout.setSpacing(4)
        
        # --- 5H Section ---
        self.five_hour_container = QWidget(self.card)
        fh_layout = QVBoxLayout(self.five_hour_container)
        fh_layout.setContentsMargins(0, 0, 0, 2)
        fh_layout.setSpacing(2)
        
        hdr_fs = max(7, int(round(11 * self.scale)))
        sub_fs = max(6, int(round(10 * self.scale)))
        
        fh_top = QHBoxLayout()
        self.fh_title_lbl = QLabel("5H", self.five_hour_container)
        self.fh_title_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.text_color};")
        self.fh_stat_lbl = QLabel("剩 100%", self.five_hour_container)
        self.fh_stat_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: #10B981; font-family: 'Consolas', monospace;")
        fh_top.addWidget(self.fh_title_lbl)
        fh_top.addStretch()
        fh_top.addWidget(self.fh_stat_lbl)
        
        pbar_h = max(3, int(round(4 * self.scale)))
        self.fh_pbar = QProgressBar(self.five_hour_container)
        self.fh_pbar.setFixedHeight(pbar_h)
        self.fh_pbar.setTextVisible(False)
        self.fh_pbar.setRange(0, 100)
        self.fh_pbar.setValue(0)
        
        lbl_h = max(11, int(round(14 * self.scale)))
        self.fh_reset_lbl = QLabel("倒计时: --", self.five_hour_container)
        self.fh_reset_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {self.subtext_color}; font-weight: 400;")
        self.fh_reset_lbl.setFixedHeight(lbl_h)
        
        self.fh_exhaust_lbl = QLabel("预计分析中...", self.five_hour_container)
        self.fh_exhaust_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: #10B981; font-weight: 700;")
        self.fh_exhaust_lbl.setFixedHeight(lbl_h)
        
        fh_layout.addLayout(fh_top)
        fh_layout.addWidget(self.fh_pbar)
        fh_layout.addWidget(self.fh_reset_lbl)
        fh_layout.addWidget(self.fh_exhaust_lbl)
        self.card_layout.addWidget(self.five_hour_container)
        self.five_hour_container.hide()
        
        # --- Weekly Window Section ---
        self.weekly_container = QWidget(self.card)
        wk_layout = QVBoxLayout(self.weekly_container)
        wk_layout.setContentsMargins(0, 0, 0, 0)
        wk_layout.setSpacing(3)
        
        stat_top = QHBoxLayout()
        self.stat_title_lbl = QLabel("周限额", self.weekly_container)
        self.stat_title_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.text_color};")
        
        self.stat_num_lbl = QLabel("剩 --", self.weekly_container)
        self.stat_num_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: #60A5FA; font-family: 'Consolas', monospace;")
        
        stat_top.addWidget(self.stat_title_lbl)
        stat_top.addStretch()
        stat_top.addWidget(self.stat_num_lbl)
        wk_layout.addLayout(stat_top)
        
        # Progress Bar
        self.pbar = QProgressBar(self.weekly_container)
        self.pbar.setFixedHeight(pbar_h)
        self.pbar.setTextVisible(False)
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        wk_layout.addWidget(self.pbar)
        
        # 7-Day Sparkline Curve with Grid
        self.sparkline = QuotaSparklineWidget(self.weekly_container, accent="#3B82F6")
        self.sparkline.set_scale(self.scale)
        self.sparkline.setFixedHeight(max(32, int(round(44 * self.scale))))
        wk_layout.addWidget(self.sparkline)
        
        # Reset Countdown (Upper Line) & Exhaustion (Lower Line, Bold)
        lbl_h = max(11, int(round(14 * self.scale)))
        self.reset_lbl = QLabel("倒计时: --", self.weekly_container)
        self.reset_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {self.subtext_color}; font-weight: 400;")
        self.reset_lbl.setFixedHeight(lbl_h)
        wk_layout.addWidget(self.reset_lbl)
        
        self.exhaust_lbl = QLabel("预计分析中...", self.weekly_container)
        self.exhaust_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: #3B82F6; font-weight: 700;")
        self.exhaust_lbl.setFixedHeight(lbl_h)
        wk_layout.addWidget(self.exhaust_lbl)
        
        self.card_layout.addWidget(self.weekly_container)
        
        # Credits remain visible only when available.
        self.credits_badge = QLabel("", self.card)
        self.credits_badge.setProperty("class", "BadgeCredits")
        self.card_layout.addWidget(self.credits_badge)
        self.update_lbl = QLabel("--:--:--", self)
        self.header_layout.insertWidget(3, self.update_lbl)
        self.update_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.update_lbl.setMinimumWidth(0)

        self.main_layout.addWidget(self.card)
        self.credits_badge.hide()
        self.set_scale(self.scale)

    def set_scale(self, scale: float):
        """Update scale and refresh typography & component sizing."""
        self.scale = max(0.5, float(scale))
        logo_sz = max(9, int(round(13 * self.scale)))
        self.logo_lbl.setPixmap(self._logo_pixmap(logo_sz))
        btn_sz = max(14, int(round(18 * self.scale)))
        self.refresh_btn.setFixedSize(btn_sz, btn_sz)
        self.sparkline.set_scale(self.scale)
        self.sparkline.setFixedHeight(max(32, int(round(44 * self.scale))))
        lbl_h = max(11, int(round(14 * self.scale)))
        self.reset_lbl.setFixedHeight(lbl_h)
        self.exhaust_lbl.setFixedHeight(lbl_h)
        self.fh_reset_lbl.setFixedHeight(lbl_h)
        self.fh_exhaust_lbl.setFixedHeight(lbl_h)
        pbar_h = max(3, int(round(4 * self.scale)))
        self.fh_pbar.setFixedHeight(pbar_h)
        self.pbar.setFixedHeight(pbar_h)
        self.main_layout.setSpacing(max(2, round(4 * self.scale)))
        self.header_layout.setSpacing(max(2, round(4 * self.scale)))
        self.card_layout.setContentsMargins(round(6 * self.scale), round(5 * self.scale), round(6 * self.scale), round(5 * self.scale))
        self.card_layout.setSpacing(max(2, round(3 * self.scale)))
        hdr_fs = max(7, round(11 * self.scale))
        sub_fs = max(6, round(10 * self.scale))
        for label in (self.fh_title_lbl, self.stat_title_lbl, self.fh_stat_lbl, self.stat_num_lbl):
            label.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.text_color};")
        for label in (self.fh_reset_lbl, self.fh_exhaust_lbl, self.reset_lbl, self.exhaust_lbl):
            label.setStyleSheet(f"font-size: {sub_fs}px; color: {self.subtext_color};")
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.title_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.subtext_color};")
        self.update_lbl.setFixedWidth(round(48 * self.scale))
        self.update_lbl.setStyleSheet(f"font-size: {max(7, round(9 * self.scale))}px; color: {self.subtext_color}; font-family: Consolas;")
        if self._last_data:
            self.update_data(self._last_data)

    def _percent(self, value):
        return str(round(float(value))) if self.provider == "Claude" else str(value)

    def set_codex_running_state(self, running: bool):
        """No-op kept for interface compatibility."""
        pass

    def update_data(self, data: Dict[str, Any]):
        """Update quota numbers with exact minute timestamps and uniform scaled font."""
        self._last_data = data
        hdr_fs = max(7, int(round(11 * self.scale)))
        sub_fs = max(6, int(round(10 * self.scale)))

        if not data.get("success"):
            err_msg = str(data.get("error", "获取失败"))
            self.weekly_container.show()
            self.sparkline.hide()
            self.reset_lbl.hide()
            self.update_lbl.setText("--:--:--")
            self.update_lbl.setToolTip(err_msg)
            self.stat_num_lbl.setText("未获取")
            self.stat_num_lbl.setStyleSheet(f"color: #EF4444; font-size: {hdr_fs}px;")
            short_err = "网络连接异常" if "Connection" in err_msg or "HTTPS" in err_msg else (err_msg[:20] + "..." if len(err_msg) > 20 else err_msg)
            self.exhaust_lbl.setText(f"提示: {short_err}")
            self.exhaust_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {self.text_color}; font-weight: 700;")
            self.exhaust_lbl.setToolTip(f"错误详情: {err_msg}")
            self.card.setToolTip(err_msg)
            self.pbar.setValue(0)
            self.credits_badge.hide()
            self.five_hour_container.hide()
            return

        self.card.setToolTip(str(data.get("error", "")) if data.get("stale") else "")
        self.exhaust_lbl.setToolTip("")
        self.reset_lbl.show()
        self.sparkline.show()

        # Update Plan badge
        plan = data.get("plan_type", "PLUS")
        self.plan_badge.setText(plan)
        
        # Record history snapshot
        self.tracker.record_snapshot(data)
        
        # 1. 5H Window
        five_h = data.get("five_hour_window")
        if five_h:
            self.five_hour_container.show()
            fh_used = five_h.get("used_percent", 0)
            fh_remain = five_h.get("remaining_percent", 100)
            fh_cd = five_h.get("reset_countdown", "")
            fh_color = five_h.get("bar_color", "#10B981")
            fh_reset_at = five_h.get("reset_at")
            
            fh_exact_dt = ""
            if fh_reset_at:
                try:
                    fh_exact_dt = datetime.fromtimestamp(fh_reset_at).strftime("%m-%d %H:%M")
                except Exception:
                    pass
            elif five_h.get("reset_at_str"):
                fh_exact_dt = five_h.get("reset_at_str")
            
            self.fh_title_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.text_color};")
            self.fh_stat_lbl.setText(f"剩 {self._percent(fh_remain)}%")
            self.fh_stat_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: {fh_color}; font-family: 'Consolas', monospace;")
            self.fh_pbar.setValue(fh_used)
            self.fh_pbar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(255, 255, 255, 0.1);
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {fh_color};
                    border-radius: 2px;
                }}
            """)
            fh_str = f"倒计时: {fh_cd}"
            if fh_exact_dt:
                fh_str += f" ({fh_exact_dt})"
            self.fh_reset_lbl.setText(fh_str)
            self.fh_reset_lbl.setToolTip(fh_str)
            self.fh_reset_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {self.subtext_color}; font-weight: 400;")
            
            # 5H Exhaustion prediction
            fh_analysis = self.tracker.get_analysis_for_current_cycle(five_h)
            if fh_analysis.get("has_data"):
                self.fh_exhaust_lbl.setText(fh_analysis.get("exhaustion_text", ""))
            else:
                self.fh_exhaust_lbl.setText("预计分析中...")
            self.fh_exhaust_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {fh_color}; font-weight: 700;")
        else:
            self.five_hour_container.hide()
        
        # 2. Weekly Window
        weekly = data.get("weekly_window") or data.get("primary_window")
        self.weekly_container.setVisible(bool(weekly))
        if weekly:
            name = weekly.get("name", "周限额")
            used = weekly.get("used_percent", 0)
            remain = weekly.get("remaining_percent", 100)
            countdown = weekly.get("reset_countdown", "")
            reset_at = weekly.get("reset_at")
            color = weekly.get("bar_color", "#3B82F6")
            
            self.stat_title_lbl.setText(name)
            self.stat_title_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 600; color: {self.text_color};")
            self.stat_num_lbl.setText(f"剩 {self._percent(remain)}%")
            self.stat_num_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: {color}; font-family: 'Consolas', monospace;")
            
            self.pbar.setValue(used)
            self.pbar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(255, 255, 255, 0.1);
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 2px;
                }}
            """)
            
            # Exact minute timestamp MM-DD HH:MM
            exact_dt_str = ""
            if reset_at:
                try:
                    exact_dt_str = datetime.fromtimestamp(reset_at).strftime("%m-%d %H:%M")
                except Exception:
                    pass
            elif weekly.get("reset_at_str"):
                exact_dt_str = weekly.get("reset_at_str")
                    
            r_str = f"倒计时: {countdown}"
            if exact_dt_str:
                r_str += f" ({exact_dt_str})"
            self.reset_lbl.setText(r_str)
            self.reset_lbl.setToolTip(r_str)
            self.reset_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {self.subtext_color}; font-weight: 400;")
            
            # Compute analytical metrics & burn curve
            analysis = self.tracker.get_analysis_for_current_cycle(weekly)
            self.sparkline.set_analysis_data(analysis)
            
            exhaust_text = analysis.get("exhaustion_text", "").replace("⚠️ ", "").replace("✅ ", "").replace("⏳ ", "")
            self.exhaust_lbl.setText(exhaust_text)
            self.exhaust_lbl.setToolTip(exhaust_text)
            self.exhaust_lbl.setStyleSheet(f"font-size: {sub_fs}px; color: {color}; font-weight: 700;")

        self.fh_exhaust_lbl.setToolTip(self.fh_exhaust_lbl.text())

        # Credits
        credits_count = data.get("reset_credits", 0)
        if credits_count > 0:
            self.credits_badge.setText(f"🎁 积分: {credits_count}")
            self.credits_badge.show()
        else:
            self.credits_badge.hide()

        # Update time
        fetch_time = data.get("fetch_time", "")
        self.update_lbl.setText(str(fetch_time)[-8:])
        tooltip = str(fetch_time)
        if data.get("stale"):
            self.update_lbl.setText(str(fetch_time)[-8:-3] + "*")
            last = data.get("fetched_at")
            when = datetime.fromtimestamp(last).strftime("%m-%d %H:%M:%S") if last else str(fetch_time)
            retry = datetime.fromtimestamp(data["retry_at"]).strftime("%H:%M:%S") if data.get("retry_at") else "稍后"
            tooltip = f"最近成功读取 {when}。{data.get('error', '')}，{retry} 自动重试。"
            self.card.setToolTip(tooltip)
        self.update_lbl.setToolTip(tooltip)
