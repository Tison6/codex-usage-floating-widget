"""
Relay Station View Widget.
Renders real-time monitored tables for Square API and AIHub.
Supports interactive group/model/provider filtering and per-provider Pelican test image thumbnails.
"""

from typing import Dict, Any, List, Optional, Set
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QScrollArea, QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRectF, QObject
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QBrush



SCROLL_STYLE = """
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollArea > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:vertical {
        border: none;
        background: rgba(255, 255, 255, 0.03);
        width: 4px;
        margin: 0px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.18);
        border-radius: 2px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(59, 130, 246, 0.5);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
"""


class SuccessRateBarWidget(QWidget):
    """
    Renders benchmark success rate sparkline:
    Vertical rounded pill bars followed by percentage text (e.g. 100.0% or 83.7%).
    Supports dynamic hourly time-series slices matching Square official website.
    """

    def __init__(self, count: int = 10, success_rate: float = 100.0, series: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self.series = series or []
        self.rate = success_rate
        self.bar_count = max(4, min(count, 12)) if not self.series else min(len(self.series), 12)
        self.setFixedHeight(14)
        self.setFixedWidth(64)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_w = 1.0
        bar_h = 8.5
        gap = 0.6
        y = (self.height() - bar_h) / 2.0

        emerald = QColor("#10B981")
        amber = QColor("#F59E0B")
        rose = QColor("#EF4444")

        x = 0.5
        if self.series:
            # Draw real historical time slices (last 12 points)
            pts = self.series[-12:]
            for pt in pts:
                sr = float(pt.get("success_rate", 100.0) or 0.0)
                if sr >= 99.0:
                    painter.setBrush(QBrush(emerald))
                elif sr >= 75.0:
                    painter.setBrush(QBrush(amber))
                else:
                    painter.setBrush(QBrush(rose))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 0.5, 0.5)
                x += bar_w + gap
        else:
            has_fail = self.rate < 99.0
            is_bad = self.rate < 75.0
            for i in range(self.bar_count):
                if is_bad:
                    painter.setBrush(QBrush(rose if i % 2 == 0 else amber))
                elif has_fail and i == self.bar_count - 2:
                    painter.setBrush(QBrush(amber))
                else:
                    painter.setBrush(QBrush(emerald))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 0.5, 0.5)
                x += bar_w + gap

        # Percentage text
        x += 2.0
        is_bad = self.rate < 75.0
        has_fail = self.rate < 99.0
        text_color = rose if is_bad else (amber if has_fail else emerald)
        painter.setPen(text_color)
        font = QFont("Segoe UI", 7, QFont.Bold)
        painter.setFont(font)

        text = f"{self.rate:.1f}%"
        rect = QRectF(x, 0, self.width() - x, self.height())
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.end()



class ThumbnailDownloadManager(QObject):
    """Central persistent manager for streaming and caching small supplier thumbnails without thread deadlocks."""
    _instance: Optional["ThumbnailDownloadManager"] = None
    _lock = threading.Lock()
    thumb_loaded = pyqtSignal(str, QImage)

    @classmethod
    def instance(cls) -> "ThumbnailDownloadManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ThumbnailDownloadManager()
            return cls._instance

    def __init__(self):
        super().__init__()
        self.cache: Dict[str, QImage] = {}
        self.in_flight: Set[str] = set()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumb_worker")
        self._thread_local = threading.local()

    def _get_session(self) -> requests.Session:
        if not hasattr(self._thread_local, "session"):
            s = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=1)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            self._thread_local.session = s
        return self._thread_local.session

    def request_thumbnail(self, url: str):
        if not url:
            return
        if url in self.cache:
            self.thumb_loaded.emit(url, self.cache[url])
            return
        if url in self.in_flight:
            return
        self.in_flight.add(url)
        self.executor.submit(self._fetch_thumb_worker, url)

    def _fetch_thumb_worker(self, url: str):
        try:
            s = self._get_session()
            resp = s.get(url, timeout=(3.0, 5.0))
            if resp.status_code == 200 and resp.content:
                qimg = QImage()
                if qimg.loadFromData(resp.content):
                    scaled = qimg.scaled(70, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.cache[url] = scaled
                    self.thumb_loaded.emit(url, scaled)
        except Exception:
            pass
        finally:
            self.in_flight.discard(url)


class ClickableThumbnail(QLabel):
    """Clickable thumbnail image representing a provider's detection artifact."""
    clicked = pyqtSignal(dict)  # emits provider_dict

    def __init__(self, provider_item: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.provider_item = provider_item
        self.setFixedSize(72, 36)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击在线查看该供应商全部历史鹈鹕图")

        has_img = provider_item.get("has_image")
        self.img_url = provider_item.get("image_url") or ""

        mgr = ThumbnailDownloadManager.instance()
        if has_img and self.img_url:
            if self.img_url in mgr.cache:
                self._apply_image(mgr.cache[self.img_url])
                return

            self.setText("📷 实测")
            self._set_loading_style()
            mgr.thumb_loaded.connect(self._on_img_loaded)
            mgr.request_thumbnail(self.img_url)
        elif has_img:
            self.setText("📷 实测")
            self._set_loading_style()
        else:
            self.setText("-")
            self._set_empty_style()

    def _set_loading_style(self):
        self.setStyleSheet("""
            QLabel {
                background: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.4);
                border-radius: 4px;
                color: #34D399;
                font-size: 9px;
                font-weight: 700;
            }
            QLabel:hover {
                background: rgba(16, 185, 129, 0.28);
                border-color: rgba(16, 185, 129, 0.8);
            }
        """)

    def _set_empty_style(self):
        self.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 4px;
                color: #64748B;
                font-size: 9px;
            }
        """)

    def _apply_image(self, scaled: QImage):
        pix = QPixmap.fromImage(scaled)
        self.setText("")
        self.setPixmap(pix)
        self.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(16, 185, 129, 0.45);
                border-radius: 4px;
            }
            QLabel:hover {
                border-color: #34D399;
                border-width: 1.5px;
            }
        """)

    def _on_img_loaded(self, url: str, scaled: QImage):
        if self.img_url == url:
            self._apply_image(scaled)


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.provider_item)
            event.accept()
        else:
            super().mousePressEvent(event)


class RelayStationView(QWidget):
    """Component for displaying Square API & AIHub live stats in expanded mode."""

    pelican_clicked = pyqtSignal(dict)  # emits provider_item dict
    filter_dialog_requested = pyqtSignal()
    aihub_filter_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tab = 0
        self._square_data: Dict[str, Any] = {}
        self._aihub_data: Dict[str, Any] = {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main Card container
        self.card = QFrame(self)
        self.card.setProperty("class", "CardSection")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 5, 6, 5)
        card_layout.setSpacing(5)

        # 1. Header with Tab Toggle
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("中转站")
        self.title_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #E2E8F0;")

        # Tab Buttons
        self.btn_square = QPushButton("Square")
        self.btn_square.setCheckable(True)
        self.btn_square.setChecked(True)
        self.btn_square.setCursor(Qt.PointingHandCursor)
        self.btn_square.setFixedHeight(20)

        self.btn_aihub = QPushButton("AIHub")
        self.btn_aihub.setCheckable(True)
        self.btn_aihub.setChecked(False)
        self.btn_aihub.setCursor(Qt.PointingHandCursor)
        self.btn_aihub.setFixedHeight(20)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setToolTip("刷新中转站数据")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 11px;
                color: #64748B;
            }
            QPushButton:hover {
                color: #38BDF8;
            }
        """)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)

        tab_btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                font-weight: 600;
                min-width: 44px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #F8FAFC;
            }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.25);
                border-color: #3B82F6;
                color: #60A5FA;
            }
        """
        self.btn_square.setStyleSheet(tab_btn_style)
        self.btn_aihub.setStyleSheet(tab_btn_style)

        self.btn_square.clicked.connect(lambda: self.switch_tab(0))
        self.btn_aihub.clicked.connect(lambda: self.switch_tab(1))

        header.addWidget(self.title_lbl)
        header.addStretch()
        header.addWidget(self.btn_square)
        header.addWidget(self.btn_aihub)
        header.addWidget(self.btn_refresh)
        card_layout.addLayout(header)

        # Divider
        div = QFrame(self.card)
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); height: 1px; border: none;")
        card_layout.addWidget(div)

        # 2. Stacked Content (Square API vs AIHub)
        self.stack = QStackedWidget(self.card)

        # Panel 0: Square API
        self.square_panel = QWidget()
        self.init_square_panel()
        self.stack.addWidget(self.square_panel)

        # Panel 1: AIHub
        self.aihub_panel = QWidget()
        self.init_aihub_panel()
        self.stack.addWidget(self.aihub_panel)

        card_layout.addWidget(self.stack)
        main_layout.addWidget(self.card)

    def init_square_panel(self):
        p_layout = QVBoxLayout(self.square_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # Sub-header with Filter Button
        sub_hdr = QHBoxLayout()
        self.sq_status_lbl = QLabel("🟢 Square (实时监控)")
        self.sq_status_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #10B981;")

        self.btn_sq_filter = QPushButton("⚙ 勾选")
        self.btn_sq_filter.setCursor(Qt.PointingHandCursor)
        self.btn_sq_filter.setToolTip("手动勾选想要监控的分组与模型")
        self.btn_sq_filter.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 3px;
                color: #60A5FA;
                font-size: 8px;
                font-weight: 600;
                padding: 1px 4px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.28);
                color: #93C5FD;
            }
        """)
        self.btn_sq_filter.clicked.connect(self.filter_dialog_requested.emit)

        sub_hdr.setSpacing(6)
        sub_hdr.addWidget(self.sq_status_lbl)
        sub_hdr.addStretch()
        sub_hdr.addWidget(self.btn_sq_filter)
        p_layout.addLayout(sub_hdr)

        # Scroll Area for Square Monitored Rows
        self.sq_scroll = QScrollArea()
        self.sq_scroll.setWidgetResizable(True)
        self.sq_scroll.setFixedHeight(260)
        self.sq_scroll.setMinimumWidth(340)
        self.sq_scroll.setStyleSheet(SCROLL_STYLE)
        self.sq_scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.sq_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.sq_scroll_content = QWidget()
        self.sq_scroll_content.setStyleSheet("background: transparent;")
        self.sq_grid = QGridLayout(self.sq_scroll_content)
        self.sq_grid.setContentsMargins(1, 1, 6, 1)
        self.sq_grid.setHorizontalSpacing(4)
        self.sq_grid.setVerticalSpacing(3)
        self.sq_scroll.setWidget(self.sq_scroll_content)
        p_layout.addWidget(self.sq_scroll)

    def init_aihub_panel(self):
        p_layout = QVBoxLayout(self.aihub_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # Sub-header with Filter Button (NO balance display per user request)
        sub_hdr = QHBoxLayout()
        self.aihub_title_lbl = QLabel("🟢 AIHub 供应商实测")
        self.aihub_title_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981;")

        self.btn_aihub_filter = QPushButton("⚙ 勾选")
        self.btn_aihub_filter.setCursor(Qt.PointingHandCursor)
        self.btn_aihub_filter.setToolTip("手动勾选想要监控的 AIHub 供应商")
        self.btn_aihub_filter.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.15);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 3px;
                color: #34D399;
                font-size: 8px;
                font-weight: 600;
                padding: 1px 4px;
            }
            QPushButton:hover {
                background: rgba(16, 185, 129, 0.28);
                color: #6EE7B7;
            }
        """)
        self.btn_aihub_filter.clicked.connect(self.aihub_filter_requested.emit)

        self.aihub_status_lbl = QLabel("实时更新")
        self.aihub_status_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

        sub_hdr.setSpacing(6)
        sub_hdr.addWidget(self.aihub_title_lbl)
        sub_hdr.addStretch()
        sub_hdr.addWidget(self.btn_aihub_filter)
        sub_hdr.addWidget(self.aihub_status_lbl)
        p_layout.addLayout(sub_hdr)

        # Scroll Area for Providers Table
        self.aihub_scroll = QScrollArea()
        self.aihub_scroll.setWidgetResizable(True)
        self.aihub_scroll.setFixedHeight(260)
        self.aihub_scroll.setMinimumWidth(340)
        self.aihub_scroll.setStyleSheet(SCROLL_STYLE)
        self.aihub_scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.aihub_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.aihub_scroll_content = QWidget()
        self.aihub_scroll_content.setStyleSheet("background: transparent;")
        self.aihub_grid = QGridLayout(self.aihub_scroll_content)
        self.aihub_grid.setContentsMargins(1, 1, 6, 1)
        self.aihub_grid.setHorizontalSpacing(4)
        self.aihub_grid.setVerticalSpacing(4)
        self.aihub_scroll.setWidget(self.aihub_scroll_content)
        p_layout.addWidget(self.aihub_scroll)

    def switch_tab(self, index: int):
        self.current_tab = index
        self.stack.setCurrentIndex(index)
        self.btn_square.setChecked(index == 0)
        self.btn_aihub.setChecked(index == 1)
        self.stack.adjustSize()
        self.card.adjustSize()
        if self.parentWidget():
            self.parentWidget().adjustSize()

    def update_square_data(self, data: Dict[str, Any]):
        """Render Square API real-time monitored performance benchmark table."""
        self._square_data = data
        if not data.get("success"):
            self.sq_status_lbl.setText(f"⚠️ {data.get('error', '获取失败')}")
            return

        balance_info = data.get("balance", {})
        used = balance_info.get("total_usage")
        if used is not None:
            self.sq_status_lbl.setText(f"🟢 Square (已用: ${used:.2f})")
        else:
            self.sq_status_lbl.setText("🟢 Square (实时监控)")

        # Clear grid
        while self.sq_grid.count():
            item = self.sq_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header Titles: 分组 / 关注模型, 倍率, 速度, 首字, 延迟, 成功率
        h_titles = ["分组 / 关注模型", "倍率", "速度", "首字", "延迟", "成功率"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.sq_grid.addWidget(h_lbl, 0, col_idx)

        monitored_rows = data.get("monitored_rows", [])
        if not monitored_rows:
            empty_lbl = QLabel("暂无勾选的分组，请点击右上角 [⚙️ 勾选监控] 选择")
            empty_lbl.setStyleSheet("font-size: 9px; color: #94A3B8; padding: 10px;")
            self.sq_grid.addWidget(empty_lbl, 1, 0, 1, 6, Qt.AlignCenter)
        else:
            for row_idx, r in enumerate(monitored_rows, start=1):
                color = r.get("color", "#10B981")
                short_g = r.get("short_name", r["group_name"][:6])
                focus_m = r.get("focus_model_display") or r.get("focus_model") or ""

                # Combined Group + Focus Model display
                g_box = QWidget()
                g_lay = QVBoxLayout(g_box)
                g_lay.setContentsMargins(0, 1, 0, 1)
                g_lay.setSpacing(1)

                g_lbl = QLabel(short_g)
                g_lbl.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {color};")
                g_lay.addWidget(g_lbl)

                if focus_m:
                    m_lbl = QLabel(focus_m)
                    m_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")
                    g_lay.addWidget(m_lbl)

                # Rich tooltip with group name, monitored models, and calculation breakdown
                breakdowns = [m.get("breakdown") for m in r.get("models", []) if m.get("breakdown")]
                calc_str = ("\n折算明细:\n  • " + "\n  • ".join(breakdowns)) if breakdowns else ""
                tip_text = (
                    f"分组: {r['group_name']}\n"
                    f"关注模型: {focus_m}\n"
                    f"分组基准倍率: {r.get('ratio_str', '--')}\n"
                    f"综合折算倍率: {r.get('effective_ratio_str', '--')}\n"
                    f"官方说明: {r.get('desc', '稳定可用')}"
                    f"{calc_str}"
                )
                g_box.setToolTip(tip_text)

                mult_lbl = QLabel(r.get("ratio_str", "--"))
                mult_lbl.setToolTip(tip_text)
                mult_lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                mult_lbl.setStyleSheet("font-size: 8px; font-weight: 600; color: #60A5FA;")

                tps_lbl = QLabel(r.get("tps", "--"))
                tps_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tps_lbl.setStyleSheet("font-size: 8px; color: #CBD5E1;")

                ttft_lbl = QLabel(r.get("ttft", "--"))
                ttft_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                ttft_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

                lat_lbl = QLabel(r.get("latency", "--"))
                lat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lat_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

                # Sparkline bar chart with live time-series
                bar_cnt = r.get("bar_count", 16)
                sr_val = float(r.get("success_rate", 100.0))
                series_data = r.get("series", [])
                bar_widget = SuccessRateBarWidget(count=bar_cnt, success_rate=sr_val, series=series_data)
                bar_widget.setToolTip(f"实测成功率: {sr_val:.1f}%\n24小时时段样本: {len(series_data)}个")

                self.sq_grid.addWidget(g_box, row_idx, 0)
                self.sq_grid.addWidget(mult_lbl, row_idx, 1)
                self.sq_grid.addWidget(tps_lbl, row_idx, 2)
                self.sq_grid.addWidget(ttft_lbl, row_idx, 3)
                self.sq_grid.addWidget(lat_lbl, row_idx, 4)
                self.sq_grid.addWidget(bar_widget, row_idx, 5, Qt.AlignRight | Qt.AlignVCenter)

        self.sq_scroll_content.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()

    def update_aihub_data(self, data: Dict[str, Any]):
        """Render AIHub monitored providers with prominent pelican thumbnails and effective multipliers."""
        self._aihub_data = data
        if not data.get("success"):
            self.aihub_status_lbl.setText("⚠️ 获取失败")
            return

        monitored = data.get("monitored_providers") or data.get("top_groups", [])

        # Display average TTFT and success rate on the top header per user suggestion
        if monitored:
            valid_tts = [g["ttft_ms"] for g in monitored if g.get("ttft_ms") and g["ttft_ms"] < 90000]
            avg_ttft = f"{sum(valid_tts)/len(valid_tts)/1000:.1f}s" if valid_tts else "--"
            valid_srs = [g["success_rate"] for g in monitored if g.get("success_rate") is not None]
            avg_sr = f"{sum(valid_srs)/len(valid_srs):.1f}%" if valid_srs else "--"
            self.aihub_status_lbl.setText(f"TTFT {avg_ttft} · 成功率 {avg_sr} · {data.get('updated_at', '')}")
        else:
            self.aihub_status_lbl.setText(f"{data.get('updated_at', '刚刚')}")

        # Clear grid
        while self.aihub_grid.count():
            item = self.aihub_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header: 供应商, 真实倍率, 缓存率, 实测图 (TTFT and 成功率 removed from main table per user request)
        h_titles = ["供应商", "真实倍率", "缓存率", "实测图"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignRight, Qt.AlignCenter]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.aihub_grid.addWidget(h_lbl, 0, col_idx)

        # Set column proportions for spacious thumbnail view
        self.aihub_grid.setColumnStretch(0, 5)
        self.aihub_grid.setColumnStretch(1, 3)
        self.aihub_grid.setColumnStretch(2, 3)
        self.aihub_grid.setColumnStretch(3, 4)

        if not monitored:
            empty_lbl = QLabel("暂无勾选的供应商，请点击右上角 [⚙️ 勾选监控] 选择")
            empty_lbl.setStyleSheet("font-size: 9px; color: #94A3B8; padding: 10px;")
            self.aihub_grid.addWidget(empty_lbl, 1, 0, 1, 4, Qt.AlignCenter)
        else:
            for row_idx, g in enumerate(monitored, start=1):
                c_name = QLabel(f"{row_idx}. {g['code']}")
                eff_mult_str = g.get("effective_multiplier_str") or g.get("multiplier_str", "--")
                nom_mult_str = g.get("multiplier_str", "--")
                tip_text = (
                    f"供应商: {g['code']}\n"
                    f"真实倍率: {eff_mult_str} (含实际缓存计费折算)\n"
                    f"名义倍率: {nom_mult_str}\n"
                    f"缓存命中率: {g.get('cache_hit_rate', '-')}\n"
                    f"首字延迟 (TTFT): {g.get('ttft_str', '--')}\n"
                    f"输出速度 (TPS): {g.get('tps_str', '--')}\n"
                    f"实测成功率: {g.get('success_rate_str', '100.0%')}"
                )
                c_name.setToolTip(tip_text)
                c_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #CBD5E1;")

                c_mult = QLabel(eff_mult_str)
                c_mult.setToolTip(tip_text)
                c_mult.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_mult.setStyleSheet("font-size: 9px; font-weight: 700; color: #34D399;")

                c_hit = QLabel(g.get("cache_hit_rate", "-"))
                c_hit.setToolTip(tip_text)
                c_hit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                c_hit.setStyleSheet("font-size: 8px; color: #94A3B8;")

                # Prominent 72x36 clickable thumbnail
                thumb = ClickableThumbnail(g, self.aihub_scroll_content)
                thumb.clicked.connect(self.pelican_clicked.emit)

                self.aihub_grid.addWidget(c_name, row_idx, 0)
                self.aihub_grid.addWidget(c_mult, row_idx, 1)
                self.aihub_grid.addWidget(c_hit, row_idx, 2)
                self.aihub_grid.addWidget(thumb, row_idx, 3, Qt.AlignCenter | Qt.AlignVCenter)

        self.aihub_scroll_content.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()
