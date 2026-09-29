"""
Pelican (鹈鹕) Test Image Viewer Dialog.
Displays all historical model detection test images for an AIHub provider in a 3-column grid,
loading them dynamically online in-memory without saving to local disk.
Engineered with zero-deadlock background worker pooling, in-memory caching, and safe lifecycle management.
"""

from typing import List, Dict, Any, Optional, Set
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import requests

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QCursor


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


class PelicanDownloadManager(QObject):
    """
    Central persistent singleton managing all image streaming and history requests.
    Uses daemon threadpool executor to eliminate all UI blocking, GIL deadlocks, and memory leaks.
    """
    _instance: Optional["PelicanDownloadManager"] = None
    _lock = threading.Lock()

    image_loaded = pyqtSignal(str, QImage)       # url, scaled_image
    history_ready = pyqtSignal(int, list)         # group_id, items
    history_error = pyqtSignal(int, str)          # group_id, error_str

    @classmethod
    def instance(cls) -> "PelicanDownloadManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = PelicanDownloadManager()
            return cls._instance

    def __init__(self):
        super().__init__()
        self.image_cache: Dict[str, QImage] = {}
        self.in_flight_urls: Set[str] = set()
        self.in_flight_histories: Set[int] = set()
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="pelican_worker")
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

    def request_history(self, aihub_client, group_id: int):
        if group_id in self.in_flight_histories:
            return
        self.in_flight_histories.add(group_id)
        self.executor.submit(self._fetch_history_worker, aihub_client, group_id)

    def _fetch_history_worker(self, aihub_client, group_id: int):
        try:
            items = aihub_client.get_provider_history_images(group_id, max_items=60)
            self.history_ready.emit(group_id, items)
        except Exception as e:
            self.history_error.emit(group_id, str(e))
        finally:
            self.in_flight_histories.discard(group_id)

    def request_image(self, url: str):
        if not url:
            return
        if url in self.image_cache:
            self.image_loaded.emit(url, self.image_cache[url])
            return
        if url in self.in_flight_urls:
            return
        self.in_flight_urls.add(url)
        self.executor.submit(self._fetch_image_worker, url)

    def _fetch_image_worker(self, url: str):
        try:
            session = self._get_session()
            resp = session.get(url, timeout=(3.0, 5.0))
            if resp.status_code == 200 and resp.content:
                qimg = QImage()
                if qimg.loadFromData(resp.content):
                    scaled = qimg.scaled(224, 114, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.image_cache[url] = scaled
                    self.image_loaded.emit(url, scaled)
        except Exception:
            pass
        finally:
            self.in_flight_urls.discard(url)


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

    def set_image(self, qimg: QImage):
        pix = QPixmap.fromImage(qimg)
        self.img_lbl.setText("")
        self.img_lbl.setPixmap(pix)

    def set_load_failed(self):
        self.img_lbl.setText("⚠️ 图片获取失败")


class PelicanViewerDialog(QDialog):
    """
    Modern dark popup dialog displaying all historical Pelican drawings for a provider
    in a 3-column responsive grid with online async streaming and zero UI freezing.
    """

    def __init__(self, provider_item: Any, aihub_client=None, operator_code: str = "", parent=None):
        super().__init__(parent)
        self.aihub_client = aihub_client
        self.cards_by_url: Dict[str, List[PelicanCard]] = {}
        self.cards_list: List[PelicanCard] = []
        self._is_closed = False

        self.total_count = 0
        self.loaded_count = 0

        # Extract provider code and group_id
        if isinstance(provider_item, dict):
            self.provider_item = provider_item
            self.operator_code = operator_code or provider_item.get("code", "AIHub")
            self.group_id = provider_item.get("group_id")
            self.initial_images = provider_item.get("operator_images", [])
        elif isinstance(provider_item, list):
            self.provider_item = {}
            self.initial_images = provider_item
            self.operator_code = operator_code or (provider_item[0].get("model_code", "AIHub") if provider_item else "AIHub")
            self.group_id = None
        else:
            self.provider_item = {}
            self.initial_images = []
            self.operator_code = operator_code or "AIHub"
            self.group_id = None

        # Connect to central download manager
        mgr = PelicanDownloadManager.instance()
        mgr.image_loaded.connect(self.on_image_loaded)
        mgr.history_ready.connect(self.on_history_data_ready)
        mgr.history_error.connect(self.on_fetch_error)

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

        # 1. Header Bar: [Code 鹈鹕] ... [✕]
        header = QHBoxLayout()
        header.setContentsMargins(2, 2, 2, 2)

        self.title_lbl = QLabel(f"{self.operator_code} 鹈鹕")
        self.title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #F1F5F9;")

        self.status_lbl = QLabel("正在连接服务器...")
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
            self.status_lbl.setText("⏳ 在线获取实测记录...")
            PelicanDownloadManager.instance().request_history(self.aihub_client, self.group_id)
        elif self.initial_images:
            self.on_history_data_ready(self.group_id or 0, self.initial_images)
        else:
            self.status_lbl.setText("⚠️ 暂无该供应商图片记录")

    def on_history_data_ready(self, group_id: int, items: List[Dict[str, Any]]):
        if self._is_closed:
            return
        if self.group_id is not None and group_id != self.group_id:
            return

        self.total_count = len(items)
        self.loaded_count = 0

        # Clear existing grid
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.cards_by_url.clear()
        self.cards_list.clear()

        if not items:
            self.status_lbl.setText("共 0 张实测图")
            empty_lbl = QLabel("暂无检测图片")
            empty_lbl.setStyleSheet("font-size: 12px; color: #94A3B8; padding: 30px;")
            self.grid.addWidget(empty_lbl, 0, 0, 1, 3, Qt.AlignCenter)
            return

        self.status_lbl.setText(f"共 {self.total_count} 张实测图 (在线实时加载中...)")

        mgr = PelicanDownloadManager.instance()
        # Build 3-column grid
        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3

            card = PelicanCard(item, self.grid_content)
            self.cards_list.append(card)
            self.grid.addWidget(card, row, col)

            img_url = item.get("url", "")
            if img_url:
                if img_url not in self.cards_by_url:
                    self.cards_by_url[img_url] = []
                self.cards_by_url[img_url].append(card)

                if img_url in mgr.image_cache:
                    card.set_image(mgr.image_cache[img_url])
                    self.loaded_count += 1
                else:
                    mgr.request_image(img_url)
            else:
                card.set_load_failed()

        if self.loaded_count >= self.total_count and self.total_count > 0:
            self.status_lbl.setText(f"共 {self.total_count} 张实测图 (全部就绪)")

        self.grid_content.adjustSize()

    def on_fetch_error(self, group_id: int, err: str):
        if self._is_closed:
            return
        if self.group_id is not None and group_id != self.group_id:
            return
        self.status_lbl.setText("⚠️ 获取失败，请检查网络")

    def on_image_loaded(self, url: str, scaled_img: QImage):
        if self._is_closed:
            return
        cards = self.cards_by_url.get(url, [])
        for card in cards:
            card.set_image(scaled_img)
            self.loaded_count += 1

        if self.total_count > 0:
            if self.loaded_count >= self.total_count:
                self.status_lbl.setText(f"共 {self.total_count} 张实测图 (全部加载完成)")
            else:
                self.status_lbl.setText(f"共 {self.total_count} 张实测图 (已加载 {self.loaded_count}/{self.total_count})")

    def _cleanup_signals(self):
        self._is_closed = True
        mgr = PelicanDownloadManager.instance()
        for sig, slot in [
            (mgr.image_loaded, self.on_image_loaded),
            (mgr.history_ready, self.on_history_data_ready),
            (mgr.history_error, self.on_fetch_error),
        ]:
            try:
                sig.disconnect(slot)
            except Exception:
                pass

    def closeEvent(self, event):
        self._cleanup_signals()
        super().closeEvent(event)

    def reject(self):
        self._cleanup_signals()
        super().reject()

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
