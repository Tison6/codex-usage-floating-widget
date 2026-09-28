"""
Compact ChatGPT / Codex View Component with 5H & Weekly Rate Limits, Grid Sparkline & Status Light.
Only shows remaining percentage, exact minute timestamps (MM-DD HH:MM),
uniform subtext font size, and dynamic status light.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.sparkline_widget import QuotaSparklineWidget
from ui.status_light import CodexStatusLight
from core.quota_tracker import QuotaTracker


class CodexQuotaView(QWidget):
    """Compact view for ChatGPT Plus / Codex usage stats & 7-Day Burn Sparkline."""
    
    refresh_requested = pyqtSignal()
    
    def __init__(self, quota_tracker: QuotaTracker, parent=None):
        super().__init__(parent)
        self.tracker = quota_tracker
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)
        
        # Header
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(2, 0, 2, 0)
        self.header_layout.setSpacing(6)
        
        self.title_lbl = QLabel("🤖 ChatGPT", self)
        self.title_lbl.setProperty("class", "SectionHeader")
        
        self.plan_badge = QLabel("PLUS", self)
        self.plan_badge.setProperty("class", "BadgePlan")
        
        self.status_light = CodexStatusLight(self, size=13)
        
        self.refresh_btn = QPushButton("🔄", self)
        self.refresh_btn.setProperty("class", "IconButton")
        self.refresh_btn.setFixedSize(18, 18)
        self.refresh_btn.setToolTip("点击立即刷新 ChatGPT 用量")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        self.header_layout.addWidget(self.title_lbl)
        self.header_layout.addWidget(self.plan_badge)
        self.header_layout.addWidget(self.status_light)
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
        
        fh_top = QHBoxLayout()
        self.fh_title_lbl = QLabel("5H", self.five_hour_container)
        self.fh_title_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #E5E7EB;")
        self.fh_stat_lbl = QLabel("剩 100%", self.five_hour_container)
        self.fh_stat_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981; font-family: 'Consolas', monospace;")
        fh_top.addWidget(self.fh_title_lbl)
        fh_top.addStretch()
        fh_top.addWidget(self.fh_stat_lbl)
        
        self.fh_pbar = QProgressBar(self.five_hour_container)
        self.fh_pbar.setFixedHeight(4)
        self.fh_pbar.setTextVisible(False)
        self.fh_pbar.setRange(0, 100)
        self.fh_pbar.setValue(0)
        
        self.fh_reset_lbl = QLabel("倒计时: --", self.five_hour_container)
        self.fh_reset_lbl.setStyleSheet("font-size: 9px; color: #9CA3AF; font-weight: 400;")
        
        fh_layout.addLayout(fh_top)
        fh_layout.addWidget(self.fh_pbar)
        fh_layout.addWidget(self.fh_reset_lbl)
        self.card_layout.addWidget(self.five_hour_container)
        self.five_hour_container.hide()
        
        # --- Weekly Window Section ---
        self.weekly_container = QWidget(self.card)
        wk_layout = QVBoxLayout(self.weekly_container)
        wk_layout.setContentsMargins(0, 0, 0, 0)
        wk_layout.setSpacing(3)
        
        stat_top = QHBoxLayout()
        self.stat_title_lbl = QLabel("周限额", self.weekly_container)
        self.stat_title_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #E5E7EB;")
        
        self.stat_num_lbl = QLabel("剩 56%", self.weekly_container)
        self.stat_num_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #60A5FA; font-family: 'Consolas', monospace;")
        
        stat_top.addWidget(self.stat_title_lbl)
        stat_top.addStretch()
        stat_top.addWidget(self.stat_num_lbl)
        wk_layout.addLayout(stat_top)
        
        # Progress Bar
        self.pbar = QProgressBar(self.weekly_container)
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.setRange(0, 100)
        self.pbar.setValue(44)
        wk_layout.addWidget(self.pbar)
        
        # 7-Day Sparkline Curve with Grid
        self.sparkline = QuotaSparklineWidget(self.weekly_container)
        self.sparkline.setFixedHeight(56)
        wk_layout.addWidget(self.sparkline)
        
        # Reset Countdown (Upper Line) & Exhaustion (Lower Line, Bold)
        self.reset_lbl = QLabel("倒计时: --", self.weekly_container)
        self.reset_lbl.setStyleSheet("font-size: 9px; color: #9CA3AF; font-weight: 400;")
        self.reset_lbl.setFixedHeight(14)
        wk_layout.addWidget(self.reset_lbl)
        
        self.exhaust_lbl = QLabel("预计分析中...", self.weekly_container)
        self.exhaust_lbl.setStyleSheet("font-size: 9px; color: #F3F4F6; font-weight: 700;")
        self.exhaust_lbl.setFixedHeight(14)
        wk_layout.addWidget(self.exhaust_lbl)
        
        self.card_layout.addWidget(self.weekly_container)
        
        # --- Footer (Credits) ---
        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(0, 2, 0, 0)
        
        self.credits_badge = QLabel("🎁 积分: 1", self.card)
        self.credits_badge.setProperty("class", "BadgeCredits")
        
        self.update_lbl = QLabel("更新: 刚刚", self.card)
        self.update_lbl.setProperty("class", "SubText")
        
        self.footer_layout.addWidget(self.credits_badge)
        self.footer_layout.addStretch()
        self.footer_layout.addWidget(self.update_lbl)
        self.card_layout.addLayout(self.footer_layout)
        
        self.main_layout.addWidget(self.card)

    def set_codex_running_state(self, running: bool):
        """Update status light state."""
        self.status_light.set_running_state(running)

    def update_data(self, data: Dict[str, Any]):
        """Update quota numbers with exact minute timestamps and uniform 9px font."""
        if not data.get("success"):
            err_msg = str(data.get("error", "获取失败"))
            self.stat_num_lbl.setText("异常")
            self.stat_num_lbl.setStyleSheet("color: #EF4444; font-size: 10px;")
            short_err = "网络连接异常" if "Connection" in err_msg or "HTTPS" in err_msg else (err_msg[:20] + "..." if len(err_msg) > 20 else err_msg)
            self.exhaust_lbl.setText(f"提示: {short_err}")
            self.exhaust_lbl.setToolTip(f"错误详情: {err_msg}")
            self.pbar.setValue(0)
            self.credits_badge.hide()
            self.five_hour_container.hide()
            return

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
            
            self.fh_stat_lbl.setText(f"剩 {fh_remain}%")
            self.fh_stat_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {fh_color}; font-family: 'Consolas', monospace;")
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
        else:
            self.five_hour_container.hide()
        
        # 2. Weekly Window
        weekly = data.get("weekly_window") or data.get("primary_window")
        if weekly:
            name = weekly.get("name", "周限额")
            used = weekly.get("used_percent", 0)
            remain = weekly.get("remaining_percent", 100)
            countdown = weekly.get("reset_countdown", "")
            reset_at = weekly.get("reset_at")
            color = weekly.get("bar_color", "#3B82F6")
            
            self.stat_title_lbl.setText(name)
            self.stat_num_lbl.setText(f"剩 {remain}%")
            self.stat_num_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {color}; font-family: 'Consolas', monospace;")
            
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
            
            # Compute analytical metrics & burn curve
            analysis = self.tracker.get_analysis_for_current_cycle(weekly)
            self.sparkline.set_analysis_data(analysis)
            
            exhaust_text = analysis.get("exhaustion_text", "").replace("⚠️ ", "").replace("✅ ", "").replace("⏳ ", "")
            self.exhaust_lbl.setText(exhaust_text)

        # Credits
        credits_count = data.get("reset_credits", 0)
        if credits_count > 0:
            self.credits_badge.setText(f"🎁 积分: {credits_count}")
            self.credits_badge.show()
        else:
            self.credits_badge.hide()

        # Update time
        fetch_time = data.get("fetch_time", "")
        self.update_lbl.setText(f"更新: {fetch_time}")
