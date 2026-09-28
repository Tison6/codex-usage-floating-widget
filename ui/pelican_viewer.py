"""
Pelican (鹈鹕) Test Image Viewer Dialog.
Displays all historical model detection test images for an AIHub provider in a 3-column grid,
loading them dynamically online in-memory without saving to local disk.
"""

from typing import List, Dict, Any, Optional
import os
import requests

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize, QRunnable, QThreadPool, QObject
from PyQt5.QtGui import QPixmap, QColor, QFont, QCursor


SCROLL_STYLE = """
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: rgba(255, 255, 255, 0.03);
        width: 6px;
        margin: 0px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 3px;
        min-height: 25px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(59, 130, 246, 0.5);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
"""


class ImageLoadSignals(QObject):
    loaded = pyqtSignal(int, bytes)
    failed = pyqtSignal(int)


class ImageDownloadTask(QRunnable):
    """Downloads an image directly into memory without writing to disk."""

    def __init__(self, item_id: int, url: str, signals: ImageLoadSignals):
        super().__init__()
        self.item_id = item_id
        self.url = url
        self.signals = signals

    def run(self):
        try:
            resp = requests.get(self.url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code == 200 and resp.content:
                self.signals.loaded.emit(self.item_id, resp.content)
            else:
                self.signals.failed.emit(self.item_id)
        except Exception:
            self.signals.failed.emit(self.item_id)


class PelicanCard(QFrame):
    """Individual card for a pelican test image with timestamp overlay."""

    def __init__(self, item_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.item_info = item_info
        self.setFixedSize(236, 150)
        self.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.07);
                border-color: rgba(56, 189, 248, 0.4);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 1. Image preview container
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setStyleSheet("background: transparent; border: none; font-size: 11px; color: #64748B;")
        self.img_lbl.setText("⏳ 加载中...")
        layout.addWidget(self.img_lbl, 1)

        # 2. Bottom timestamp bar
        time_str = item_info.get("published_at_str", "")
        if not time_str and item_info.get("published_at"):
            raw_t = item_info["published_at"]
            try:
                time_str = raw_t[:19].replace("T", " ")
            except Exception:
                time_str = raw_t

        self.time_lbl = QLabel(time_str)
        self.time_lbl.setAlignment(Qt.AlignCenter)
        self.time_lbl.setStyleSheet("""
            background: rgba(15, 23, 42, 0.85);
            color: #CBD5E1;
            font-size: 10px;
            font-weight: 600;
            border-radius: 4px;
            padding: 2px 4px;
            border: 1px solid rgba(255, 255, 255, 0.06);
        """)
        layout.addWidget(self.time_lbl)

    def set_image_bytes(self, data: bytes):
        pix = QPixmap()
        if pix.loadFromData(data) and not pix.isNull():
            scaled = pix.scaled(QSize(224, 114), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_lbl.setPixmap(scaled)
        else:
            self.img_lbl.setText("⚠️ 解析失败")

    def set_load_failed(self):
        self.img_lbl.setText("⚠️ 图片获取失败")


class HistoryFetchThread(QThread):
    """Thread for querying AIHub API for all historical images of a provider."""
    data_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, aihub_client, group_id: int):
        super().__init__()
        self.aihub_client = aihub_client
        self.group_id = group_id

    def run(self):
        try:
            items = self.aihub_client.get_provider_history_images(self.group_id, max_items=60)
            self.data_ready.emit(items)
        except Exception as e:
            self.error_occurred.emit(str(e))


class PelicanViewerDialog(QDialog):
    """
    Modern dark popup dialog displaying all historical Pelican drawings for a provider
    in a 3-column responsive grid with online async loading.
    """

    def __init__(self, provider_item: Any, aihub_client=None, operator_code: str = "", parent=None):
        super().__init__(parent)
        self.aihub_client = aihub_client
        self.cards_map: Dict[int, PelicanCard] = {}
        self.thread_pool = QThreadPool.globalInstance()

        # Extract provider code and group_id
        if isinstance(provider_item, dict):
            self.provider_item = provider_item
            self.operator_code = operator_code or provider_item.get("code", "AIHub")
            self.group_id = provider_item.get("group_id")
            self.initial_images = provider_item.get("operator_images", [])
        elif isinstance(provider_item, list):
            # Backward compatibility
            self.provider_item = {}
            self.initial_images = provider_item
            self.operator_code = operator_code or (provider_item[0].get("model_code", "AIHub") if provider_item else "AIHub")
            self.group_id = None
        else:
            self.provider_item = {}
            self.initial_images = []
            self.operator_code = operator_code or "AIHub"
            self.group_id = None

        self.signals = ImageLoadSignals()
        self.signals.loaded.connect(self.on_image_loaded)
        self.signals.failed.connect(self.on_image_failed)

        self.init_window()
        self.init_ui()

        # Fetch history online
        self.load_images()

    def init_window(self):
        self.setWindowTitle(f"{self.operator_code} 鹈鹕")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(780, 580)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        container = QWidget(self)
        container.setObjectName("PelicanContainer")
        container.setStyleSheet("""
            QWidget#PelicanContainer {
                background-color: rgba(20, 24, 33, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # 1. Header Bar matching screenshot: [Code 鹈鹕] ... [✕]
        header = QHBoxLayout()
        header.setContentsMargins(2, 2, 2, 2)

        self.title_lbl = QLabel(f"{self.operator_code} 鹈鹕")
        self.title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #F1F5F9;")

        self.status_lbl = QLabel("正在加载...")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; margin-left: 8px;")

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94A3B8;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.3);
                color: #EF4444;
            }
        """)
        btn_close.clicked.connect(self.close)

        header.addWidget(self.title_lbl)
        header.addWidget(self.status_lbl)
        header.addStretch()
        header.addWidget(btn_close)
        layout.addLayout(header)

        # 2. Scroll Area for 3-Column Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(SCROLL_STYLE)
        self.scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_content = QWidget()
        self.grid_content.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_content)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(12)

        self.scroll.setWidget(self.grid_content)
        layout.addWidget(self.scroll, 1)

        root.addWidget(container)

    def load_images(self):
        if self.aihub_client and self.group_id is not None:
            self.status_lbl.setText("⏳ 在线获取实测历史...")
            self.fetch_thread = HistoryFetchThread(self.aihub_client, self.group_id)
            self.fetch_thread.data_ready.connect(self.on_history_data_ready)
            self.fetch_thread.error_occurred.connect(self.on_fetch_error)
            self.fetch_thread.start()
        elif self.initial_images:
            self.on_history_data_ready(self.initial_images)
        else:
            self.status_lbl.setText("⚠️ 暂无该供应商图片记录")

    def on_history_data_ready(self, items: List[Dict[str, Any]]):
        self.status_lbl.setText(f"共 {len(items)} 张实测图 (在线实时加载)")

        # Clear existing grid
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.cards_map.clear()

        if not items:
            empty_lbl = QLabel("暂无检测图片")
            empty_lbl.setStyleSheet("font-size: 12px; color: #94A3B8; padding: 30px;")
            self.grid.addWidget(empty_lbl, 0, 0, 1, 3, Qt.AlignCenter)
            return

        # Build 3-column grid
        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3

            card = PelicanCard(item, self.grid_content)
            self.cards_map[idx] = card
            self.grid.addWidget(card, row, col)

            # Spawn async download into memory
            img_url = item.get("url", "")
            if img_url:
                task = ImageDownloadTask(idx, img_url, self.signals)
                self.thread_pool.start(task)
            else:
                card.set_load_failed()

        self.grid_content.adjustSize()

    def on_fetch_error(self, err: str):
        self.status_lbl.setText("⚠️ 获取失败，请检查网络")

    def on_image_loaded(self, item_id: int, data: bytes):
        card = self.cards_map.get(item_id)
        if card:
            card.set_image_bytes(data)

    def on_image_failed(self, item_id: int):
        card = self.cards_map.get(item_id)
        if card:
            card.set_load_failed()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
