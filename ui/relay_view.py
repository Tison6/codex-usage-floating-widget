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
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRectF, QObject, QEvent
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QBrush, QFontMetrics, QPen



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
    QScrollBar:horizontal {
        border: none;
        background: rgba(255, 255, 255, 0.05);
        height: 9px;
        margin: 0px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal {
        background: rgba(255, 255, 255, 0.28);
        border-radius: 4px;
        min-width: 32px;
    }
    QScrollBar::handle:horizontal:hover {
        background: rgba(56, 189, 248, 0.75);
    }
    QScrollBar::handle:horizontal:pressed {
        background: rgba(56, 189, 248, 0.95);
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
"""


def interpolate_color(c1, c2, ratio: float):
    return tuple(int(round(a + (b - a) * ratio)) for a, b in zip(c1, c2))

COLOR_RED = (239, 68, 68)      # #EF4444 (85% and below / 0.20 and above)
COLOR_YELLOW = (245, 158, 11)  # #F59E0B (midpoint)
COLOR_GREEN = (16, 185, 129)   # #10B981 (100% / 0.10 and below)

def get_metric_color(val: Optional[float], min_v: float, max_v: float, higher_is_better: bool = True) -> str:
    """
    Compute smooth gradient color between Red, Yellow, and Green.
    - If higher_is_better (Cache, Success Rate):
        val <= min_v -> Red
        val >= max_v -> Green
        min_v < val < max_v -> gradient Red -> Yellow -> Green
    - If not higher_is_better (Multiplier):
        val <= min_v -> Green (0.10 and below)
        val >= max_v -> Red (0.20 and above)
        min_v < val < max_v -> gradient Green -> Yellow -> Red
    """
    if val is None:
        return "#64748B"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return "#64748B"

    v = max(min_v, min(max_v, v))
    t = (v - min_v) / (max_v - min_v) if max_v > min_v else 1.0
    if not higher_is_better:
        t = 1.0 - t

    if t <= 0.5:
        rgb = interpolate_color(COLOR_RED, COLOR_YELLOW, t / 0.5)
    else:
        rgb = interpolate_color(COLOR_YELLOW, COLOR_GREEN, (t - 0.5) / 0.5)
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

def format_multi_gradient_html(val_str: str, min_v: float, max_v: float, higher_is_better: bool = True) -> str:
    """Format slash-separated multi-period stats with individually colored values."""
    if not val_str or val_str == "--":
        return "<span style='color: #64748B;'>--</span>"
    parts = val_str.split("/")
    html_parts = []
    slash_html = "<span style='color: #475569;'>/</span>"
    for p in parts:
        clean_p = p.strip()
        num_str = clean_p.replace("%", "").replace("x", "").strip()
        try:
            num = float(num_str)
            color = get_metric_color(num, min_v, max_v, higher_is_better)
            html_parts.append(f"<span style='color: {color};'>{clean_p}</span>")
        except ValueError:
            html_parts.append(f"<span style='color: #64748B;'>{clean_p}</span>")
    return slash_html.join(html_parts)



class DetectionDot(QWidget):
    """
    Compact circular status dot for AIHub model verification status:
    - passed: emerald green (#10B981)
    - suspected: electric amber orange (#F59E0B)
    - other/none: muted slate gray (#64748B)
    Renders as a clean single circular dot without any background oval.
    Clicking emits clicked(str) to open 24h history timeline.
    """
    clicked = pyqtSignal(str)

    def __init__(self, status: str = "other", tooltip: str = "", size: int = 7, parent=None):
        super().__init__(parent)
        self.status = status
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_status(self, status: str, tooltip: str = ""):
        self.status = status
        if tooltip:
            self.setToolTip(tooltip)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.status)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        if self.status == "passed":
            color = QColor("#10B981")
        elif self.status == "suspected":
            color = QColor("#F59E0B")
        else:
            color = QColor("#64748B")

        dot_d = max(4.0, float(self._size))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF((w - dot_d) / 2.0, (h - dot_d) / 2.0, dot_d, dot_d))
        painter.end()


class CandyDot(QWidget):
    """
    Compact circular status dot for AIHub candy question test result (糖果题):
    - correct (通过 / 21): emerald green (#10B981)
    - wrong (未通过 / 非21): rose red (#EF4444)
    - none/empty (无数据): muted slate gray (#64748B)
    Renders as a circular dot matching DetectionDot.
    Clicking emits clicked(str) to open 24h history timeline.
    """
    clicked = pyqtSignal(str)

    def __init__(self, status: str = "none", label: str = "--", scale: float = 1.0, tooltip: str = "", size: int = 7, parent=None):
        super().__init__(parent)
        self.scale = max(0.5, float(scale))
        self.status = status
        self.label = label
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_data(self, status: str, label: str = "--", tooltip: str = ""):
        self.status = status
        self.label = label
        if tooltip:
            self.setToolTip(tooltip)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.status)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        if self.status == "correct":
            color = QColor("#10B981")
        elif self.status == "wrong":
            color = QColor("#EF4444")
        else:
            color = QColor("#64748B")

        dot_d = max(4.0, float(self._size))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF((w - dot_d) / 2.0, (h - dot_d) / 2.0, dot_d, dot_d))
        painter.end()


# Backward compatibility alias
CandyBadge = CandyDot


class ProviderNameLabel(QWidget):
    """
    Renders provider index + code (bold whitish) and optional public detail (grey subtext).
    Uses a compact 2-line vertical layout when detail is present, ensuring detail is always
    cleanly visible and never clipped horizontally by the code name.
    """
    def __init__(self, code: str, detail: str = "", scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.code = code
        self.detail = detail
        self.scale = max(0.5, float(scale))
        self._init_fonts()
        self.setCursor(Qt.PointingHandCursor)

    def _init_fonts(self):
        code_px = max(6, int(round(7.0 * self.scale)))
        det_px = max(5, int(round(5.8 * self.scale)))
        self.code_font = QFont("Segoe UI")
        self.code_font.setPixelSize(code_px)
        self.code_font.setBold(True)
        self.det_font = QFont("Segoe UI")
        self.det_font.setPixelSize(det_px)

    def set_scale(self, scale: float):
        self.scale = max(0.5, float(scale))
        self._init_fonts()
        self.update()

    def set_data(self, code: str, detail: str = ""):
        if self.code != code or self.detail != detail:
            self.code = code
            self.detail = detail
            self.update()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setClipRect(self.rect())

            avail_w = max(10, self.width() - 2)
            fm_code = QFontMetrics(self.code_font)
            is_off = "[下架]" in self.code
            name_color = QColor("#94A3B8") if is_off else QColor("#CBD5E1")
            if self.detail:
                # 2-line layout: Line 1 = Code name, Line 2 = Grey subtext
                painter.setFont(self.code_font)
                painter.setPen(name_color)
                elided_code = fm_code.elidedText(self.code, Qt.ElideRight, avail_w)
                y_code = fm_code.ascent() + 2
                painter.drawText(0, y_code, elided_code)

                painter.setFont(self.det_font)
                painter.setPen(QColor("#EF4444") if is_off else QColor("#64748B"))
                fm_det = QFontMetrics(self.det_font)
                disp_det = "[官方大厅已下架]" if is_off else self.detail
                elided_det = fm_det.elidedText(disp_det, Qt.ElideRight, avail_w)
                y_det = self.height() - fm_det.descent() - 2
                painter.drawText(0, y_det, elided_det)
            else:
                # Single line layout: vertically centered
                painter.setFont(self.code_font)
                painter.setPen(name_color)
                elided_code = fm_code.elidedText(self.code, Qt.ElideRight, avail_w)
                y_base = int((self.height() + fm_code.ascent() - fm_code.descent()) / 2)
                painter.drawText(0, y_base, elided_code)
            painter.end()
        except Exception:
            pass


class SuccessRateBarWidget(QWidget):
    """
    Renders benchmark success rate sparkline:
    Vertical rounded pill bars followed by percentage text (e.g. 100.0% or 83.7%).
    Supports dynamic hourly time-series slices matching Square official website.
    """

    def __init__(self, count: int = 8, success_rate: float = 100.0, series: Optional[List[Dict[str, Any]]] = None, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.series = series or []
        self.rate = success_rate
        self.scale = max(0.5, float(scale))
        self.bar_count = max(4, min(count, 8)) if not self.series else min(len(self.series), 8)
        self.setFixedHeight(14)
        self.setFixedWidth(max(44, int(round(52 * self.scale))))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_data(self, rate: float, series: Optional[List[Dict[str, Any]]] = None):
        self.rate = rate
        self.series = series or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_w = 1.0
        bar_h = 7.5
        gap = 0.5
        y = (self.height() - bar_h) / 2.0

        emerald = QColor("#10B981")
        amber = QColor("#F59E0B")
        rose = QColor("#EF4444")

        x = 0.5
        if self.series:
            # Draw real historical time slices (last 6 points)
            pts = self.series[-6:]
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
        x += 1.5
        is_bad = self.rate < 75.0
        has_fail = self.rate < 99.0
        text_color = rose if is_bad else (amber if has_fail else emerald)
        painter.setPen(text_color)
        font = QFont("Segoe UI", max(5, int(round(7 * self.scale))), QFont.Bold)
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
                    scaled = qimg.scaled(46, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.cache[url] = scaled
                    self.thumb_loaded.emit(url, scaled)
        except Exception:
            pass
        finally:
            self.in_flight.discard(url)


class ClickableThumbnail(QWidget):
    """Clickable thumbnail image representing a provider's detection artifact."""
    clicked = pyqtSignal(dict)  # emits provider_dict

    def __init__(self, provider_item: Dict[str, Any], parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.provider_item = provider_item
        self.scale = max(0.5, float(scale))
        w = max(30, int(round(36 * self.scale)))
        h = max(15, int(round(18 * self.scale)))
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击在线查看该供应商全部历史鹈鹕图")
        self._hovered = False
        self._pixmap = None

        has_img = provider_item.get("has_image")
        self.img_url = provider_item.get("image_url") or ""

        mgr = ThumbnailDownloadManager.instance()
        if has_img and self.img_url:
            if self.img_url in mgr.cache:
                self.apply_image(mgr.cache[self.img_url])
            else:
                self.state = "loading"
                mgr.request_thumbnail(self.img_url)
        elif has_img:
            self.state = "loading"
        else:
            self.state = "empty"

    def set_data(self, provider_item: Dict[str, Any]):
        self.provider_item = provider_item
        has_img = provider_item.get("has_image")
        new_img_url = provider_item.get("image_url") or ""
        if self.img_url != new_img_url:
            self.img_url = new_img_url
            self._pixmap = None
            mgr = ThumbnailDownloadManager.instance()
            if has_img and self.img_url:
                if self.img_url in mgr.cache:
                    self.apply_image(mgr.cache[self.img_url])
                else:
                    self.state = "loading"
                    mgr.request_thumbnail(self.img_url)
            elif has_img:
                self.state = "loading"
            else:
                self.state = "empty"
        elif has_img and self.img_url and getattr(self, "state", "") != "image":
            mgr = ThumbnailDownloadManager.instance()
            if self.img_url in mgr.cache:
                self.apply_image(mgr.cache[self.img_url])
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def apply_image(self, scaled: QImage):
        try:
            from PyQt5 import sip
            if sip.isdeleted(self):
                return
            pix = QPixmap.fromImage(scaled)
            if not pix.isNull():
                self._pixmap = pix.scaled(self.width() - 2, self.height() - 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.state = "image"
                self.update()
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        r = 3.0

        st = getattr(self, "state", "empty")
        if st == "image" and self._pixmap and not self._pixmap.isNull():
            painter.fillRect(rect, QColor(0, 0, 0, 100))
            px_x = int((self.width() - self._pixmap.width()) / 2)
            px_y = int((self.height() - self._pixmap.height()) / 2)
            painter.drawPixmap(px_x, px_y, self._pixmap)
            border_col = QColor("#34D399") if self._hovered else QColor(16, 185, 129, 115)
            pen = QPen(border_col, 1.5 if self._hovered else 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, r, r)
        elif st == "loading":
            bg_col = QColor(16, 185, 129, 70 if self._hovered else 30)
            border_col = QColor(16, 185, 129, 200 if self._hovered else 100)
            painter.setPen(QPen(border_col, 1.0))
            painter.setBrush(bg_col)
            painter.drawRoundedRect(rect, r, r)
            painter.setPen(QColor("#34D399"))
            font = QFont("Segoe UI", max(6, int(round(7.5 * self.scale))), QFont.Bold)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "📷 实测")
        else:
            bg_col = QColor(255, 255, 255, 8)
            border_col = QColor(255, 255, 255, 15)
            painter.setPen(QPen(border_col, 1.0))
            painter.setBrush(bg_col)
            painter.drawRoundedRect(rect, r, r)
            painter.setPen(QColor("#64748B"))
            font = QFont("Segoe UI", max(6, int(round(7.5 * self.scale))))
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "-")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.provider_item)
            event.accept()
        else:
            super().mousePressEvent(event)

class FrozenLeftScrollArea(QScrollArea):
    """
    Pinned left-column scroll area for AIHub table.
    Hides scrollbars and forwards mouse wheel vertical scrolling to the right scroll area.
    """
    def __init__(self, target_scroll: Optional[QScrollArea] = None, parent=None):
        super().__init__(parent)
        self.target_scroll = target_scroll

    def set_target_scroll(self, target_scroll: QScrollArea):
        self.target_scroll = target_scroll

    def wheelEvent(self, event):
        if self.target_scroll:
            delta = event.angleDelta().y()
            bar = self.target_scroll.verticalScrollBar()
            if bar:
                step = bar.singleStep() or 20
                num_steps = delta / 120.0
                bar.setValue(int(round(bar.value() - num_steps * step * 2)))
                event.accept()
                return
        super().wheelEvent(event)


class RelayStationView(QWidget):
    """Component for displaying Square API & AIHub live stats in expanded mode."""

    pelican_clicked = pyqtSignal(dict)  # emits provider_item dict
    filter_dialog_requested = pyqtSignal()
    aihub_filter_requested = pyqtSignal()
    history_timeline_requested = pyqtSignal(str, str)  # emits (provider_code, dimension)
    refresh_requested = pyqtSignal()
    aihub_mode_toggled = pyqtSignal(bool)  # emits new auto_mode boolean (True=auto, False=manual)

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = max(0.5, float(scale))
        self.current_tab = 0
        self._square_data: Dict[str, Any] = {}
        self._aihub_data: Dict[str, Any] = {}
        self._active_thumbnails: List[ClickableThumbnail] = []
        self._sq_rows: List[Dict[str, Any]] = []
        self._aihub_rows: List[Dict[str, Any]] = []
        self.sq_empty_lbl = None
        self.aihub_empty_lbl = None
        self.aihub_empty_left = None
        try:
            ThumbnailDownloadManager.instance().thumb_loaded.connect(self._on_thumbnail_loaded, Qt.QueuedConnection)
        except Exception:
            pass
        self.init_ui()

    def _clear_sq_rows(self):
        for entry in self._sq_rows:
            for w in (entry.get("g_box"), entry.get("mult"), entry.get("out_price"), entry.get("tps"), entry.get("ttft"), entry.get("lat"), entry.get("bar")):
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        self._sq_rows.clear()
        if hasattr(self, "sq_grid") and self.sq_grid:
            for i in reversed(range(self.sq_grid.count())):
                item = self.sq_grid.itemAt(i)
                if item:
                    row, col, rspan, cspan = self.sq_grid.getItemPosition(i)
                    if row > 0:
                        w = item.widget()
                        self.sq_grid.removeItem(item)
                        if w:
                            w.hide()
                            w.setParent(None)
                            w.deleteLater()

    def _clear_aihub_rows(self):
        for entry in self._aihub_rows:
            for w in (entry.get("dot"), entry.get("candy"), entry.get("name"), entry.get("nom"), entry.get("thumb"), entry.get("eff"), entry.get("hit"), entry.get("sr"), entry.get("ref")):
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        self._aihub_rows.clear()
        self._active_thumbnails.clear()
        for grid in (getattr(self, "aihub_grid_left", None), getattr(self, "aihub_grid_right", None)):
            if grid is not None:
                while grid.count():
                    item = grid.takeAt(0)
                    w = item.widget()
                    if w:
                        w.hide()
                        w.setParent(None)
                        w.deleteLater()

    def _on_thumbnail_loaded(self, url: str, scaled: QImage):
        for thumb in list(self._active_thumbnails):
            try:
                from PyQt5 import sip
                if not sip.isdeleted(thumb) and getattr(thumb, "img_url", None) == url:
                    thumb.apply_image(scaled)
            except Exception:
                pass

    def set_scale(self, scale: float):
        """Update scale and re-render header and tables."""
        self.scale = max(0.5, float(scale))
        self._apply_header_styles()
        self._clear_sq_rows()
        self._clear_aihub_rows()
        table_h = max(150, int(round(240 * self.scale)))
        hdr_row_h = max(18, int(round(20 * self.scale)))
        left_w = (
            max(14, int(round(15 * self.scale))) +
            max(18, int(round(20 * self.scale))) +
            max(54, int(round(62 * self.scale))) +
            max(2, int(round(2 * self.scale)))
        )
        right_w = (
            max(22, int(round(25 * self.scale))) +
            max(32, int(round(38 * self.scale))) +
            max(92, int(round(108 * self.scale))) +
            max(80, int(round(92 * self.scale))) +
            max(60, int(round(70 * self.scale))) +
            max(50, int(round(58 * self.scale))) +
            max(16, int(round(20 * self.scale)))
        )
        if hasattr(self, "sq_scroll"):
            self.sq_scroll.setFixedHeight(table_h)
        if hasattr(self, "aihub_table_container"):
            self.aihub_table_container.setFixedHeight(table_h)
        if hasattr(self, "aihub_left_container"):
            self.aihub_left_container.setFixedWidth(left_w)
            self.aihub_left_container.setFixedHeight(table_h)
        if hasattr(self, "aihub_header_left"):
            self.aihub_header_left.setFixedHeight(hdr_row_h)
            self.aihub_header_left.setFixedWidth(left_w)
        if hasattr(self, "aihub_scroll_left"):
            self.aihub_scroll_left.setFixedWidth(left_w)
            self.aihub_scroll_left.setFixedHeight(table_h - hdr_row_h - 9)
        if hasattr(self, "aihub_scroll_content_left"):
            self.aihub_scroll_content_left.setFixedWidth(left_w)
        if hasattr(self, "aihub_sep"):
            self.aihub_sep.setFixedHeight(table_h - 9)
        if hasattr(self, "aihub_right_container"):
            self.aihub_right_container.setFixedHeight(table_h)
        if hasattr(self, "aihub_header_scroll_right"):
            self.aihub_header_scroll_right.setFixedHeight(hdr_row_h)
        if hasattr(self, "aihub_header_content_right"):
            self.aihub_header_content_right.setMinimumWidth(right_w)
        if hasattr(self, "aihub_scroll_right"):
            self.aihub_scroll_right.setFixedHeight(table_h - hdr_row_h)
        if hasattr(self, "aihub_scroll"):
            self.aihub_scroll.setFixedHeight(table_h - hdr_row_h)
        if hasattr(self, "aihub_scroll_content_right"):
            self.aihub_scroll_content_right.setMinimumWidth(right_w)

        # Safely clear and rebuild permanent headers on zoom/scale change
        header_grids = [self.sq_grid]
        if hasattr(self, "aihub_header_grid_left") and self.aihub_header_grid_left:
            header_grids.append(self.aihub_header_grid_left)
        if hasattr(self, "aihub_header_grid_right") and self.aihub_header_grid_right:
            header_grids.append(self.aihub_header_grid_right)
        for grid in header_grids:
            for i in reversed(range(grid.count())):
                item = grid.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    grid.removeItem(item)
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        self._init_square_headers()
        self._init_aihub_headers()

        if self._square_data:
            self.update_square_data(self._square_data)
        if self._aihub_data:
            self.update_aihub_data(self._aihub_data)

    def _apply_header_styles(self):
        title_fs = max(7, int(round(10 * self.scale)))
        self.title_lbl.setStyleSheet(f"font-size: {title_fs}px; font-weight: 700; color: #E2E8F0;")
        tab_h = max(16, int(round(20 * self.scale)))
        self.btn_square.setFixedHeight(tab_h)
        self.btn_aihub.setFixedHeight(tab_h)
        btn_sz = max(16, int(round(20 * self.scale)))
        self.btn_refresh.setFixedSize(btn_sz, btn_sz)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main Card container
        self.card = QFrame(self)
        self.card.setProperty("class", "CardSection")
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 5, 6, 5)
        card_layout.setSpacing(5)

        # 1. Header with Tab Toggle
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title_fs = max(7, int(round(10 * self.scale)))
        self.title_lbl = QLabel("中转站")
        self.title_lbl.setStyleSheet(f"font-size: {title_fs}px; font-weight: 700; color: #E2E8F0;")

        tab_h = max(16, int(round(20 * self.scale)))
        # Tab Buttons
        self.btn_square = QPushButton("Square")
        self.btn_square.setCheckable(True)
        self.btn_square.setChecked(True)
        self.btn_square.setCursor(Qt.PointingHandCursor)
        self.btn_square.setFixedHeight(tab_h)

        self.btn_aihub = QPushButton("AIHub")
        self.btn_aihub.setCheckable(True)
        self.btn_aihub.setChecked(False)
        self.btn_aihub.setCursor(Qt.PointingHandCursor)
        self.btn_aihub.setFixedHeight(tab_h)

        btn_sz = max(16, int(round(20 * self.scale)))
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(btn_sz, btn_sz)
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
        self.sq_scroll.setFixedHeight(max(150, int(round(240 * self.scale))))
        self.sq_scroll.setStyleSheet(SCROLL_STYLE)
        self.sq_scroll.viewport().setStyleSheet("background-color: #171C25; border: none;")
        self.sq_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.sq_scroll_content = QWidget()
        self.sq_scroll_content.setStyleSheet("background-color: #171C25;")
        self.sq_grid = QGridLayout(self.sq_scroll_content)
        self.sq_grid.setContentsMargins(1, 1, 2, 1)
        self.sq_grid.setHorizontalSpacing(3)
        self.sq_grid.setVerticalSpacing(2)
        self.sq_scroll.setWidget(self.sq_scroll_content)
        p_layout.addWidget(self.sq_scroll)
        self._init_square_headers()

    def init_aihub_panel(self):
        p_layout = QVBoxLayout(self.aihub_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # Sub-header with Filter Button (NO balance display per user request)
        sub_hdr = QHBoxLayout()
        self.aihub_title_lbl = QLabel("🟢 AIHub 实测")
        self.aihub_title_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981;")

        # Mode button (Auto vs Manual)
        self.btn_aihub_mode = QPushButton("🤖 自动")
        self.btn_aihub_mode.setCursor(Qt.PointingHandCursor)
        self.btn_aihub_mode.setToolTip("点击切换：自动筛选(按默认阈值每分钟更新) / 手动勾选")
        self.btn_aihub_mode.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.18);
                border: 1px solid rgba(16, 185, 129, 0.4);
                border-radius: 3px;
                color: #34D399;
                font-size: 8px;
                font-weight: 700;
                padding: 1px 4px;
            }
            QPushButton:hover {
                background: rgba(16, 185, 129, 0.32);
                color: #6EE7B7;
            }
        """)
        self.btn_aihub_mode.clicked.connect(self.toggle_aihub_mode)

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

        self.btn_aihub_history = QPushButton("📊 历史")
        self.btn_aihub_history.setCursor(Qt.PointingHandCursor)
        self.btn_aihub_history.setToolTip("查看 AIHub 探针检测与糖果题 24h 历史时序图")
        self.btn_aihub_history.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 3px;
                color: #38BDF8;
                font-size: 8px;
                font-weight: 600;
                padding: 1px 4px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.28);
                color: #7DD3FC;
            }
        """)
        self.btn_aihub_history.clicked.connect(lambda: self.history_timeline_requested.emit("", "detection"))

        self.aihub_status_lbl = QLabel("实时更新")
        self.aihub_status_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

        sub_hdr.setSpacing(4)
        sub_hdr.addWidget(self.aihub_title_lbl)
        sub_hdr.addStretch()
        sub_hdr.addWidget(self.btn_aihub_mode)
        sub_hdr.addWidget(self.btn_aihub_filter)
        sub_hdr.addWidget(self.btn_aihub_history)
        sub_hdr.addWidget(self.aihub_status_lbl)
        p_layout.addLayout(sub_hdr)

        table_h = max(150, int(round(240 * self.scale)))
        hdr_row_h = max(18, int(round(20 * self.scale)))
        left_w = (
            max(14, int(round(15 * self.scale))) +
            max(18, int(round(20 * self.scale))) +
            max(54, int(round(62 * self.scale))) +
            max(2, int(round(2 * self.scale)))
        )
        right_w = (
            max(22, int(round(25 * self.scale))) +
            max(32, int(round(38 * self.scale))) +
            max(92, int(round(108 * self.scale))) +
            max(80, int(round(92 * self.scale))) +
            max(60, int(round(70 * self.scale))) +
            max(50, int(round(58 * self.scale))) +
            max(16, int(round(20 * self.scale)))
        )

        # AIHub dual-scroll frozen table structure: pinned left columns + scrollable right columns
        self.aihub_table_container = QWidget()
        self.aihub_table_container.setFixedHeight(table_h)
        self.aihub_table_container.setStyleSheet("background: transparent;")
        table_layout = QHBoxLayout(self.aihub_table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        table_layout.setAlignment(Qt.AlignTop)

        # Left frozen column container (fixed width)
        self.aihub_left_container = QWidget()
        self.aihub_left_container.setFixedWidth(left_w)
        self.aihub_left_container.setFixedHeight(table_h)
        self.aihub_left_container.setStyleSheet("background: transparent;")
        left_vbox = QVBoxLayout(self.aihub_left_container)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(0)
        left_vbox.setAlignment(Qt.AlignTop)

        # Left fixed header widget (never scrolls vertically)
        self.aihub_header_left = QWidget()
        self.aihub_header_left.setFixedHeight(hdr_row_h)
        self.aihub_header_left.setFixedWidth(left_w)
        self.aihub_header_left.setStyleSheet("background-color: #171C25;")
        self.aihub_header_grid_left = QGridLayout(self.aihub_header_left)
        self.aihub_header_grid_left.setContentsMargins(1, 0, 2, 0)
        self.aihub_header_grid_left.setHorizontalSpacing(1)
        self.aihub_header_grid_left.setVerticalSpacing(0)
        self.aihub_header_grid_left.setAlignment(Qt.AlignVCenter)
        left_vbox.addWidget(self.aihub_header_left)

        # Right container holds right fixed header + right data scroll area
        self.aihub_right_container = QWidget()
        self.aihub_right_container.setFixedHeight(table_h)
        self.aihub_right_container.setStyleSheet("background: transparent;")
        right_vbox = QVBoxLayout(self.aihub_right_container)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(0)
        right_vbox.setAlignment(Qt.AlignTop)

        # Right data scrollable area (created before header and left scroll so they can reference it)
        self.aihub_scroll_right = QScrollArea()
        self.aihub_scroll_right.setFrameShape(QFrame.NoFrame)
        self.aihub_scroll_right.setFixedHeight(table_h - hdr_row_h)
        self.aihub_scroll_right.setWidgetResizable(True)
        self.aihub_scroll_right.setStyleSheet(SCROLL_STYLE)
        self.aihub_scroll_right.viewport().setStyleSheet("background-color: #171C25; border: none;")
        self.aihub_scroll_right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.aihub_scroll_right.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.aihub_scroll_content_right = QWidget()
        self.aihub_scroll_content_right.setStyleSheet("background-color: #171C25;")
        self.aihub_scroll_content_right.setMinimumWidth(right_w)
        self.aihub_grid_right = QGridLayout(self.aihub_scroll_content_right)
        self.aihub_grid_right.setContentsMargins(1, 0, 2, 0)
        self.aihub_grid_right.setHorizontalSpacing(1)
        self.aihub_grid_right.setVerticalSpacing(2)
        self.aihub_grid_right.setAlignment(Qt.AlignTop)
        self.aihub_scroll_right.setWidget(self.aihub_scroll_content_right)

        # Right fixed header scroll area (syncs horizontally with right data table, never scrolls vertically)
        self.aihub_header_scroll_right = FrozenLeftScrollArea(target_scroll=self.aihub_scroll_right)
        self.aihub_header_scroll_right.setFrameShape(QFrame.NoFrame)
        self.aihub_header_scroll_right.setFixedHeight(hdr_row_h)
        self.aihub_header_scroll_right.setWidgetResizable(True)
        self.aihub_header_scroll_right.setStyleSheet(SCROLL_STYLE)
        self.aihub_header_scroll_right.viewport().setStyleSheet("background-color: #171C25; border: none;")
        self.aihub_header_scroll_right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.aihub_header_scroll_right.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.aihub_header_content_right = QWidget()
        self.aihub_header_content_right.setStyleSheet("background-color: #171C25;")
        self.aihub_header_content_right.setMinimumWidth(right_w)
        self.aihub_header_grid_right = QGridLayout(self.aihub_header_content_right)
        self.aihub_header_grid_right.setContentsMargins(1, 0, 2, 0)
        self.aihub_header_grid_right.setHorizontalSpacing(1)
        self.aihub_header_grid_right.setVerticalSpacing(0)
        self.aihub_header_grid_right.setAlignment(Qt.AlignVCenter)
        self.aihub_header_scroll_right.setWidget(self.aihub_header_content_right)

        right_vbox.addWidget(self.aihub_header_scroll_right)
        right_vbox.addWidget(self.aihub_scroll_right)

        # Left frozen data scroll area
        self.aihub_scroll_left = FrozenLeftScrollArea(target_scroll=self.aihub_scroll_right)
        self.aihub_scroll_left.setFrameShape(QFrame.NoFrame)
        self.aihub_scroll_left.setFixedWidth(left_w)
        self.aihub_scroll_left.setFixedHeight(table_h - hdr_row_h - 9)
        self.aihub_scroll_left.setWidgetResizable(True)
        self.aihub_scroll_left.setStyleSheet(SCROLL_STYLE)
        self.aihub_scroll_left.viewport().setStyleSheet("background-color: #171C25; border: none;")
        self.aihub_scroll_left.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.aihub_scroll_left.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.aihub_scroll_content_left = QWidget()
        self.aihub_scroll_content_left.setFixedWidth(left_w)
        self.aihub_scroll_content_left.setStyleSheet("background-color: #171C25;")
        self.aihub_grid_left = QGridLayout(self.aihub_scroll_content_left)
        self.aihub_grid_left.setContentsMargins(1, 0, 2, 0)
        self.aihub_grid_left.setHorizontalSpacing(1)
        self.aihub_grid_left.setVerticalSpacing(2)
        self.aihub_grid_left.setAlignment(Qt.AlignTop)
        self.aihub_scroll_left.setWidget(self.aihub_scroll_content_left)
        left_vbox.addWidget(self.aihub_scroll_left)

        # Left bottom dummy bar to match right horizontal scrollbar height (9px)
        self.aihub_left_dummy = QWidget()
        self.aihub_left_dummy.setFixedHeight(9)
        self.aihub_left_dummy.setStyleSheet("background: transparent;")
        left_vbox.addWidget(self.aihub_left_dummy)

        # Bi-directional vertical scroll synchronization between left and right data tables
        self.aihub_scroll_right.verticalScrollBar().valueChanged.connect(
            self.aihub_scroll_left.verticalScrollBar().setValue
        )
        self.aihub_scroll_left.verticalScrollBar().valueChanged.connect(
            self.aihub_scroll_right.verticalScrollBar().setValue
        )

        # Horizontal scroll synchronization between right data table and right fixed header
        self.aihub_scroll_right.horizontalScrollBar().valueChanged.connect(
            self.aihub_header_scroll_right.horizontalScrollBar().setValue
        )

        # Subtle vertical separator line between frozen left columns and scrollable right columns
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(table_h - 9)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); width: 1px; border: none;")
        self.aihub_sep = sep

        table_layout.addWidget(self.aihub_left_container)
        table_layout.addWidget(sep)
        table_layout.addWidget(self.aihub_right_container)

        p_layout.addWidget(self.aihub_table_container)

        # Aliases for backward compatibility
        self.aihub_scroll = self.aihub_scroll_right
        self.aihub_scroll_content = self.aihub_scroll_content_right
        self.aihub_grid = self.aihub_grid_right

        self._init_aihub_headers()

    def _init_square_headers(self):
        """Build permanent header row for Square table (never deleted on refresh)."""
        hdr_fs = max(6, int(round(8.5 * self.scale)))
        h_titles = ["分组/模型", "倍率", "输出/M", "速度", "首字", "延迟", "成功率"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight]
        sq_col_widths = [
            None,
            max(22, int(round(26 * self.scale))),
            max(26, int(round(30 * self.scale))),
            max(32, int(round(38 * self.scale))),
            max(26, int(round(32 * self.scale))),
            max(26, int(round(32 * self.scale))),
            max(46, int(round(52 * self.scale))),
        ]
        for col_idx, (title, align, col_w) in enumerate(zip(h_titles, h_aligns, sq_col_widths)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: #64748B;")
            if col_w:
                h_lbl.setFixedWidth(col_w)
            self.sq_grid.addWidget(h_lbl, 0, col_idx)

        self.sq_grid.setColumnStretch(0, 1)
        for c in range(1, 7):
            self.sq_grid.setColumnStretch(c, 0)

    def _init_aihub_headers(self):
        """Build permanent fixed header rows for AIHub (locked at top, never scrolled out vertically)."""
        hdr_fs = max(6, int(round(7.5 * self.scale)))
        left_h_titles = ["检测", "糖果", "供应商"]
        left_h_aligns = [Qt.AlignCenter, Qt.AlignCenter, Qt.AlignLeft]
        left_col_widths = [
            max(14, int(round(15 * self.scale))),
            max(14, int(round(15 * self.scale))),
            max(58, int(round(66 * self.scale))),
        ]

        for col_idx, (title, align, col_w) in enumerate(zip(left_h_titles, left_h_aligns, left_col_widths)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: #64748B;")
            if col_w:
                h_lbl.setFixedWidth(col_w)
            if title == "检测":
                h_lbl.setToolTip("模型真实性检测:\n🟢 检测通过 (官方验证通过)\n🟠 模型疑似 (验证无法定论)\n⚪ 其他 (证据不足/未配置)\n💡 点击下方圆点可查看 24h 历史时序图")
            elif title == "糖果":
                h_lbl.setToolTip("AIHub 糖果题实测:\n🟢 通过 (回答: 21)\n🔴 未通过 (回答非21)\n⚪ --: 暂无实测\n💡 点击下方圆点可查看 24h 历史时序图")
            elif title == "供应商":
                h_lbl.setToolTip("供应商通道与名称 (固定列，左右滑动时始终固定在左侧)")
            self.aihub_header_grid_left.addWidget(h_lbl, 0, col_idx)

        for c_i in range(3):
            self.aihub_header_grid_left.setColumnStretch(c_i, 0)
            self.aihub_grid_left.setColumnStretch(c_i, 0)

        right_h_titles = [
            "倍率", "实测图",
            "真实倍率(现/1h/1d/7d)", "缓存率(现/1h/1d/7d)", "成功率(现/1h/1d/7d)", "参考缓存率"
        ]
        right_h_aligns = [
            Qt.AlignCenter, Qt.AlignCenter,
            Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter
        ]
        right_col_widths = [
            max(22, int(round(25 * self.scale))),
            max(32, int(round(38 * self.scale))),
            max(92, int(round(108 * self.scale))),
            max(80, int(round(92 * self.scale))),
            max(80, int(round(92 * self.scale))),
            max(50, int(round(58 * self.scale))),
        ]

        for col_idx, (title, align, col_w) in enumerate(zip(right_h_titles, right_h_aligns, right_col_widths)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet(f"font-size: {hdr_fs}px; font-weight: 700; color: #64748B;")
            if col_w:
                h_lbl.setFixedWidth(col_w)
            if "真实倍率" in title:
                h_lbl.setToolTip("真实倍率 (当前 / 1小时 / 1天 / 7天):\n• 现: 在线获取当前瞬时值\n• 1h/1d/7d: 全部基于本地数据库历史采样独立计算滑动均值 (需分别累积1h/2h/72h以上)\n• <=0.10: 绿色\n• >=0.20: 红色\n• 0.10~0.20: 渐变")
            elif "缓存率" in title and "参考" not in title:
                h_lbl.setToolTip("缓存命中率 (当前 / 1小时 / 1天 / 7天):\n• 现: 在线获取当前瞬时值\n• 1h/1d/7d: 全部基于本地数据库历史采样独立计算滑动均值 (需分别累积1h/2h/72h以上)\n• 100%: 绿色\n• <=85%: 红色\n• 85%~100%: 渐变")
            elif "成功率" in title or "通过率" in title:
                h_lbl.setToolTip("接口成功率 (当前 / 1小时 / 1天 / 7天):\n• 现: 在线获取当前瞬时值\n• 1h/1d/7d: 全部基于本地数据库历史采样独立计算滑动均值 (需分别累积1h/2h/72h以上)\n• 100%: 绿色\n• <=90%: 红色\n• 90%~100%: 渐变")
            elif "参考缓存率" in title:
                h_lbl.setToolTip("官方参考缓存率基准:\n来自接口 runtime_cache_1h 的 reference_cache_hit_rate\n(全网模型统一参考缓存基准)")
            self.aihub_header_grid_right.addWidget(h_lbl, 0, col_idx)

        for c_i in range(6):
            self.aihub_header_grid_right.setColumnStretch(c_i, 0)
            self.aihub_grid_right.setColumnStretch(c_i, 0)

    def toggle_aihub_mode(self):
        """Toggle between AIHub automatic threshold filter mode and manual checked selection mode."""
        cur_auto = self._aihub_data.get("auto_mode", True)
        new_mode = not cur_auto
        self.aihub_mode_toggled.emit(new_mode)

    def switch_tab(self, index: int):
        self.current_tab = index
        self.stack.setCurrentIndex(index)
        self.btn_square.setChecked(index == 0)
        self.btn_aihub.setChecked(index == 1)

    def update_square_data(self, data: Dict[str, Any]):
        """Render Square API real-time monitored performance benchmark table with output/M token price."""
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

        row_title_fs = max(7, int(round(9.5 * self.scale)))
        row_sub_fs = max(6, int(round(8 * self.scale)))
        sq_col_widths = [
            None,
            max(22, int(round(26 * self.scale))),
            max(26, int(round(30 * self.scale))),
            max(32, int(round(38 * self.scale))),
            max(26, int(round(32 * self.scale))),
            max(26, int(round(32 * self.scale))),
            max(46, int(round(52 * self.scale))),
        ]

        monitored_rows = data.get("monitored_rows", [])
        if not monitored_rows:
            if not self.sq_empty_lbl:
                self.sq_empty_lbl = QLabel()
                self.sq_empty_lbl.setFont(QFont("Segoe UI", row_title_fs))
                self.sq_empty_lbl.setText("<span style='color: #94A3B8; padding: 10px;'>暂无勾选的分组，请点击右上角 [⚙️ 勾选监控] 选择</span>")
                self.sq_grid.addWidget(self.sq_empty_lbl, 1, 0, 1, 7, Qt.AlignCenter)
            self.sq_empty_lbl.show()
            for extra in self._sq_rows:
                for w in (extra["g_box"], extra["mult"], extra["out_price"], extra["tps"], extra["ttft"], extra["lat"], extra["bar"]):
                    w.hide()
            return

        if self.sq_empty_lbl:
            self.sq_empty_lbl.hide()

        font_title = QFont("Segoe UI", row_title_fs, QFont.Bold)
        font_sub = QFont("Segoe UI", row_sub_fs)
        font_sub_bold = QFont("Segoe UI", row_sub_fs, QFont.Bold)

        for row_idx, r in enumerate(monitored_rows, start=1):
            color = r.get("color", "#10B981")
            short_g = r.get("short_name", r["group_name"][:6])
            focus_m = r.get("focus_model_display") or r.get("focus_model") or ""

            breakdowns = [m.get("breakdown") for m in r.get("models", []) if m.get("breakdown")]
            calc_str = ("\n折算明细:\n  • " + "\n  • ".join(breakdowns)) if breakdowns else ""
            tip_text = (
                f"分组: {r['group_name']}\n"
                f"关注模型: {focus_m}\n"
                f"分组基准倍率: {r.get('ratio_str', '--')}\n"
                f"综合折算倍率: {r.get('effective_ratio_str', '--')}\n"
                f"输出价格: {r.get('output_price_tip', r.get('output_price', '--'))}\n"
                f"官方说明: {r.get('desc', '稳定可用')}"
                f"{calc_str}"
            )

            bar_cnt = r.get("bar_count", 8)
            sr_val = float(r.get("success_rate", 100.0))
            series_data = r.get("series", [])

            if row_idx - 1 < len(self._sq_rows):
                entry = self._sq_rows[row_idx - 1]
                entry["g_lbl"].setText(f"<span style='color: {color}; font-weight: 700;'>{short_g}</span>")
                if focus_m:
                    entry["m_lbl"].setText(f"<span style='color: #94A3B8;'>{focus_m}</span>")
                    entry["m_lbl"].show()
                else:
                    entry["m_lbl"].hide()
                entry["g_box"].setToolTip(tip_text)
                entry["mult"].setText(f"<span style='color: #60A5FA; font-weight: 600;'>{r.get('ratio_str', '--')}</span>")
                entry["mult"].setToolTip(tip_text)
                entry["out_price"].setText(f"<span style='color: #F59E0B; font-weight: 700;'>{r.get('output_price', '—')}</span>")
                entry["out_price"].setToolTip(r.get("output_price_tip") or "输出 token 价格")
                entry["tps"].setText(f"<span style='color: #CBD5E1;'>{r.get('tps', '--')}</span>")
                entry["ttft"].setText(f"<span style='color: #94A3B8;'>{r.get('ttft', '--')}</span>")
                entry["lat"].setText(f"<span style='color: #94A3B8;'>{r.get('latency', '--')}</span>")
                entry["bar"].set_data(sr_val, series_data)
                entry["bar"].setToolTip(f"实测成功率: {sr_val:.1f}%\n24小时时段样本: {len(series_data)}个")
                for w in (entry["g_box"], entry["mult"], entry["out_price"], entry["tps"], entry["ttft"], entry["lat"], entry["bar"]):
                    w.show()
            else:
                g_box = QWidget()
                g_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                g_lay = QVBoxLayout(g_box)
                g_lay.setContentsMargins(0, 1, 0, 1)
                g_lay.setSpacing(1)

                g_lbl = QLabel()
                g_lbl.setFont(font_title)
                g_lbl.setText(f"<span style='color: {color}; font-weight: 700;'>{short_g}</span>")
                g_lay.addWidget(g_lbl)

                m_lbl = QLabel()
                m_lbl.setFont(font_sub)
                if focus_m:
                    m_lbl.setText(f"<span style='color: #94A3B8;'>{focus_m}</span>")
                    m_lbl.show()
                else:
                    m_lbl.hide()
                g_lay.addWidget(m_lbl)
                g_box.setToolTip(tip_text)

                mult_lbl = QLabel()
                mult_lbl.setFont(font_sub_bold)
                mult_lbl.setText(f"<span style='color: #60A5FA; font-weight: 600;'>{r.get('ratio_str', '--')}</span>")
                mult_lbl.setToolTip(tip_text)
                mult_lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                mult_lbl.setFixedWidth(sq_col_widths[1])

                out_price_lbl = QLabel()
                out_price_lbl.setFont(font_sub_bold)
                out_price_lbl.setText(f"<span style='color: #F59E0B; font-weight: 700;'>{r.get('output_price', '—')}</span>")
                out_price_lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                out_price_lbl.setFixedWidth(sq_col_widths[2])
                out_price_lbl.setToolTip(r.get("output_price_tip") or "输出 token 价格")

                tps_lbl = QLabel()
                tps_lbl.setFont(font_sub)
                tps_lbl.setText(f"<span style='color: #CBD5E1;'>{r.get('tps', '--')}</span>")
                tps_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tps_lbl.setFixedWidth(sq_col_widths[3])

                ttft_lbl = QLabel()
                ttft_lbl.setFont(font_sub)
                ttft_lbl.setText(f"<span style='color: #94A3B8;'>{r.get('ttft', '--')}</span>")
                ttft_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                ttft_lbl.setFixedWidth(sq_col_widths[4])

                lat_lbl = QLabel()
                lat_lbl.setFont(font_sub)
                lat_lbl.setText(f"<span style='color: #94A3B8;'>{r.get('latency', '--')}</span>")
                lat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lat_lbl.setFixedWidth(sq_col_widths[5])

                bar_widget = SuccessRateBarWidget(count=bar_cnt, success_rate=sr_val, series=series_data, scale=self.scale)
                bar_widget.setFixedWidth(sq_col_widths[6])
                bar_widget.setToolTip(f"实测成功率: {sr_val:.1f}%\n24小时时段样本: {len(series_data)}个")

                self.sq_grid.addWidget(g_box, row_idx, 0)
                self.sq_grid.addWidget(mult_lbl, row_idx, 1)
                self.sq_grid.addWidget(out_price_lbl, row_idx, 2)
                self.sq_grid.addWidget(tps_lbl, row_idx, 3)
                self.sq_grid.addWidget(ttft_lbl, row_idx, 4)
                self.sq_grid.addWidget(lat_lbl, row_idx, 5)
                self.sq_grid.addWidget(bar_widget, row_idx, 6, Qt.AlignRight | Qt.AlignVCenter)

                self._sq_rows.append({
                    "g_box": g_box, "g_lbl": g_lbl, "m_lbl": m_lbl,
                    "mult": mult_lbl, "out_price": out_price_lbl,
                    "tps": tps_lbl, "ttft": ttft_lbl, "lat": lat_lbl, "bar": bar_widget
                })

        for extra in self._sq_rows[len(monitored_rows):]:
            for w in (extra["g_box"], extra["mult"], extra["out_price"], extra["tps"], extra["ttft"], extra["lat"], extra["bar"]):
                w.hide()

    def update_aihub_data(self, data: Dict[str, Any]):
        """Render AIHub monitored providers with prominent pelican thumbnails and effective multipliers."""
        self._aihub_data = data
        if not data.get("success"):
            self.aihub_status_lbl.setText("⚠️ 获取失败")
            return

        # Update mode button appearance
        is_auto = bool(data.get("auto_mode", True))
        if is_auto:
            self.btn_aihub_mode.setText("🤖 自动")
            self.btn_aihub_mode.setStyleSheet("""
                QPushButton {
                    background: rgba(16, 185, 129, 0.2);
                    border: 1px solid rgba(16, 185, 129, 0.5);
                    border-radius: 3px;
                    color: #34D399;
                    font-size: 8px;
                    font-weight: 700;
                    padding: 1px 4px;
                }
                QPushButton:hover {
                    background: rgba(16, 185, 129, 0.35);
                    color: #6EE7B7;
                }
            """)
            self.btn_aihub_mode.setToolTip("当前为【自动模式】(按默认阈值每分钟动态更新)\n点击切换为【手动模式】")
        else:
            self.btn_aihub_mode.setText("✋ 手动")
            self.btn_aihub_mode.setStyleSheet("""
                QPushButton {
                    background: rgba(59, 130, 246, 0.2);
                    border: 1px solid rgba(59, 130, 246, 0.5);
                    border-radius: 3px;
                    color: #60A5FA;
                    font-size: 8px;
                    font-weight: 700;
                    padding: 1px 4px;
                }
                QPushButton:hover {
                    background: rgba(59, 130, 246, 0.35);
                    color: #93C5FD;
                }
            """)
            self.btn_aihub_mode.setToolTip("当前为【手动模式】(按勾选项监控)\n点击切换为【自动模式】")

        monitored = data.get("monitored_providers") or data.get("top_groups", [])

        # Display average TTFT and success rate on the top header per user suggestion
        if monitored:
            valid_tts = [g["ttft_ms"] for g in monitored if g.get("ttft_ms") and g["ttft_ms"] < 90000]
            avg_ttft = f"{sum(valid_tts)/len(valid_tts)/1000:.1f}s" if valid_tts else "--"
            valid_srs = [g["success_rate"] for g in monitored if g.get("success_rate") is not None]
            avg_sr = f"{sum(valid_srs)/len(valid_srs):.1f}%" if valid_srs else "--"
            up_time = str(data.get('updated_at', ''))
            time_part = up_time[-8:-3] if len(up_time) >= 8 else up_time
            self.aihub_status_lbl.setText(f"{avg_ttft} · {avg_sr} · {time_part}")
            self.aihub_status_lbl.setToolTip(f"平均首字 (TTFT): {avg_ttft}\n平均成功率: {avg_sr}\n更新时间: {up_time}")
        else:
            up_time = str(data.get('updated_at', '刚刚'))
            time_part = up_time[-8:-3] if len(up_time) >= 8 else up_time
            self.aihub_status_lbl.setText(f"{time_part}")

        table_h = max(150, int(round(240 * self.scale)))
        hdr_row_h = max(18, int(round(20 * self.scale)))
        self.aihub_table_container.setFixedHeight(table_h)
        self.aihub_left_container.setFixedHeight(table_h)
        self.aihub_scroll_left.setFixedHeight(table_h - hdr_row_h - 9)
        self.aihub_scroll_right.setFixedHeight(table_h - hdr_row_h)
        if hasattr(self, "aihub_right_container"):
            self.aihub_right_container.setFixedHeight(table_h)
        if hasattr(self, "aihub_header_left"):
            self.aihub_header_left.setFixedHeight(hdr_row_h)
        if hasattr(self, "aihub_header_scroll_right"):
            self.aihub_header_scroll_right.setFixedHeight(hdr_row_h)
        if hasattr(self, "aihub_sep"):
            self.aihub_sep.setFixedHeight(table_h - 9)

        row_title_fs = max(7, int(round(8.5 * self.scale)))
        row_sub_fs = max(6, int(round(7.5 * self.scale)))
        row_multi_fs = max(6, int(round(7.5 * self.scale)))

        left_col_widths = [
            max(14, int(round(15 * self.scale))),   # 0: 检测 (单圆点居中，极简紧凑)
            max(14, int(round(15 * self.scale))),   # 1: 糖果 (单圆点居中，通过/不通过)
            max(58, int(round(66 * self.scale))),   # 2: 供应商 (代号+双行灰色小字，紧凑留出右侧空间)
        ]
        right_col_widths = [
            max(22, int(round(25 * self.scale))),   # 0: 倍率
            max(32, int(round(38 * self.scale))),   # 1: 实测图
            max(92, int(round(108 * self.scale))),  # 2: 真实倍率(现/1h/1d/7d)
            max(80, int(round(92 * self.scale))),   # 3: 缓存率(现/1h/1d/7d)
            max(60, int(round(70 * self.scale))),   # 4: 成功率(1h/1d/7d)
            max(50, int(round(58 * self.scale))),   # 5: 参考缓存率
        ]

        if not monitored:
            if not self.aihub_empty_lbl:
                self.aihub_empty_lbl = QLabel()
                self.aihub_empty_lbl.setFont(QFont("Segoe UI", row_title_fs))
                self.aihub_empty_lbl.setText("<span style='color: #94A3B8; padding: 10px;'>暂无勾选的供应商，请点击右上角 [⚙️ 勾选监控] 选择</span>")
                self.aihub_grid_right.addWidget(self.aihub_empty_lbl, 0, 0, 1, 6, Qt.AlignCenter)
            if not self.aihub_empty_left:
                self.aihub_empty_left = QLabel()
                self.aihub_empty_left.setFont(QFont("Segoe UI", row_title_fs))
                self.aihub_empty_left.setText("<span style='color: #94A3B8; padding: 10px;'>暂无数据</span>")
                self.aihub_grid_left.addWidget(self.aihub_empty_left, 0, 0, 1, 3, Qt.AlignCenter)
            self.aihub_empty_lbl.show()
            self.aihub_empty_left.show()
            for extra in self._aihub_rows:
                for w in (extra["dot"], extra.get("candy"), extra["name"], extra["nom"], extra["thumb"], extra["eff"], extra["hit"], extra["sr"], extra["ref"]):
                    if w:
                        w.hide()
            return

        if self.aihub_empty_lbl:
            self.aihub_empty_lbl.hide()
        if self.aihub_empty_left:
            self.aihub_empty_left.hide()

        dot_size = max(5, int(round(6 * self.scale)))
        data_row_h = max(22, int(round(24 * self.scale)))
        font_title = QFont("Segoe UI", row_title_fs, QFont.Bold)
        font_mono = QFont("Consolas", row_multi_fs, QFont.Bold)

        for row_idx, g in enumerate(monitored):
            self.aihub_grid_left.setRowMinimumHeight(row_idx, data_row_h)
            self.aihub_grid_right.setRowMinimumHeight(row_idx, data_row_h)

            det_status = g.get("detection_status", "other")
            det_tip = g.get("detection_tip", "模型检测: ⚪ 未配置 / 暂无检测数据") + "\n💡 点击圆点查看 24h 历史时序图"
            candy_status = g.get("candy_status", "none")
            candy_label = g.get("candy_label", "--")
            candy_tip = g.get("candy_tip", "糖果题: ⚪ 暂无实测数据") + "\n💡 点击圆点查看 24h 历史时序图"
            candy_dot_emoji = g.get("candy_dot", "⚪")
            detail = (g.get("public_detail") or "").strip() or "公开供应商线路"
            is_on = bool(g.get("available", True)) and bool(g.get("visible_in_hall", True))
            code_text = f"{row_idx + 1}. {g['code']}" + ("" if is_on else " [下架]")

            eff_mult_str = g.get("effective_multiplier_str") or "--"
            if not g.get("effective_multiplier_ready") and g.get("effective_multiplier_reason"):
                eff_mult_str = f"-- ({g['effective_multiplier_reason']})"
            eff_multi_str = g.get("effective_multiplier_multi_str") or "--/--/--/--"
            cache_multi_str = g.get("cache_hit_multi_str") or f"{g.get('cache_hit_rate', '-')}/--/--/--"
            sr_multi_str = g.get("success_rate_multi_str") or "--/--/--"
            nom_mult_str = g.get("multiplier_str", "--")
            det_label = g.get("detection_label", "未检")
            det_dot_emoji = g.get("detection_dot", "⚪")
            price_str = g.get("effective_input_price_str", "--")
            tip_text = (
                f"供应商: {g['code']}\n"
                f"模型检测: {det_dot_emoji} {det_label}\n"
                f"糖果题: {candy_dot_emoji} {candy_label}\n"
                f"标准倍率: {nom_mult_str}\n"
                f"真实折算倍率: {eff_mult_str}\n"
                f"折算输入单价: {price_str}\n"
                f"当前实测缓存率: {g.get('cache_hit_rate', '-')}\n"
                f"当前实测成功率: {g.get('success_rate_str', '--')}\n"
                f"真实倍率(现/1h/1d/7d): {eff_multi_str}\n"
                f"缓存率(现/1h/1d/7d): {cache_multi_str}\n"
                f"成功率(现/1h/1d/7d): {sr_multi_str}\n"
                f"参考缓存基准: {g.get('reference_cache_hit_rate', '--')}\n"
                f"首字延迟 (TTFT): {g.get('ttft_str', '--')}\n"
                f"输出速度 (TPS): {g.get('tps_str', '--')}\n"
                f"💡 点击前方检测或糖果圆点可查看 24h 历史时序图"
            )
            if not is_on:
                err_cat = g.get('error_category')
                off_desc = f"探针异常: {err_cat}" if err_cat else "官方大厅未在架/服务异常"
                tip_text += f"\n⚠️ [官网状态]: 当前大厅已下架 ({off_desc})"
            if detail:
                tip_text += f"\n官方说明: {detail}"
            if g.get("detection_model"):
                tip_text += f"\n检测目标: {g['detection_model']}"

            nom_val = g.get("rate_multiplier", 1.0)
            nom_color = get_metric_color(nom_val, 0.10, 0.20, higher_is_better=False)
            html_eff = format_multi_gradient_html(eff_multi_str, min_v=0.10, max_v=0.20, higher_is_better=False)
            html_hit = format_multi_gradient_html(cache_multi_str, min_v=85.0, max_v=100.0, higher_is_better=True)
            html_sr = format_multi_gradient_html(sr_multi_str, min_v=90.0, max_v=100.0, higher_is_better=True)

            ref_cache_str = g.get("reference_cache_hit_rate", "--")
            ref_cache_val = g.get("reference_cache_val")
            if ref_cache_val is not None:
                ref_color = get_metric_color(ref_cache_val, 85.0, 100.0, higher_is_better=True)
            else:
                ref_color = "#64748B"

            span_h = g.get('hist_span_hours', 0.0)
            span_note = f"• 1h/1d/7d 全部基于本地采集历史独立计算滑动均值 (已累积 {span_h:.1f}h，7d需满72h)"
            eff_tip = f"真实倍率 (现/1h/1d/7d):\n{eff_multi_str}\n• 现: 当前瞬时倍率 ({price_str})\n{span_note}\n• <=0.10: 绿色\n• >=0.20: 红色\n• 0.10~0.20: 渐变"
            hit_tip = f"缓存命中率 (现/1h/1d/7d):\n{cache_multi_str}\n• 现: 当前实测缓存率 ({g.get('cache_hit_rate', '-')})\n{span_note}\n• 100%: 绿色\n• <=85%: 红色\n• 85%~100%: 渐变"
            sr_tip = f"接口请求成功率 (现/1h/1d/7d):\n{sr_multi_str}\n• 现: 当前实测成功率 ({g.get('success_rate_str', '--')})\n{span_note}\n• 100%: 绿色\n• <=90%: 红色\n• 90%~100%: 渐变"

            if row_idx < len(self._aihub_rows):
                entry = self._aihub_rows[row_idx]
                entry["code"] = g["code"]
                entry["dot"].set_status(det_status, tooltip=det_tip)
                if "candy" in entry:
                    entry["candy"].set_data(candy_status, candy_label, tooltip=candy_tip)
                entry["name"].set_data(code_text, detail=detail)
                entry["dot"].setToolTip(tip_text)
                entry["name"].setToolTip(tip_text)

                entry["nom"].setText(f"<span style='color: {nom_color}; font-weight: 700;'>{nom_mult_str}</span>")
                entry["nom"].setToolTip(tip_text)
                entry["thumb"].set_data(g)
                entry["eff"].setText(html_eff)
                entry["eff"].setToolTip(eff_tip)
                entry["hit"].setText(html_hit)
                entry["hit"].setToolTip(hit_tip)
                entry["sr"].setText(html_sr)
                entry["sr"].setToolTip(sr_tip)
                entry["ref"].setText(f"<span style='color: {ref_color}; font-weight: 600;'>{ref_cache_str}</span>")
                entry["ref"].setToolTip(f"官方参考缓存率基准:\n{ref_cache_str} ({g.get('code')})\n(来自官方 runtime_cache_1h 全网参考缓存基准)")

                for w in (entry["dot"], entry.get("candy"), entry["name"], entry["nom"], entry["thumb"], entry["eff"], entry["hit"], entry["sr"], entry["ref"]):
                    if w:
                        w.show()
            else:
                entry_dict = {"code": g["code"]}
                c_dot = DetectionDot(det_status, tooltip=det_tip, size=dot_size, parent=self.aihub_scroll_content_left)
                c_dot.setFixedWidth(left_col_widths[0])
                c_dot.setToolTip(tip_text)
                c_dot.clicked.connect(lambda _, e=entry_dict: self.history_timeline_requested.emit(e.get("code", ""), "detection"))

                c_candy = CandyDot(candy_status, candy_label, scale=self.scale, tooltip=candy_tip, size=dot_size, parent=self.aihub_scroll_content_left)
                c_candy.setFixedWidth(left_col_widths[1])
                c_candy.setToolTip(candy_tip)
                c_candy.clicked.connect(lambda _, e=entry_dict: self.history_timeline_requested.emit(e.get("code", ""), "candy"))

                c_name = ProviderNameLabel(code_text, detail=detail, scale=self.scale, parent=self.aihub_scroll_content_left)
                c_name.setFixedWidth(left_col_widths[2])
                c_name.setFixedHeight(data_row_h)
                c_name.setToolTip(tip_text)

                c_nom = QLabel()
                c_nom.setFont(font_title)
                c_nom.setText(f"<span style='color: {nom_color}; font-weight: 700;'>{nom_mult_str}</span>")
                c_nom.setToolTip(tip_text)
                c_nom.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_nom.setFixedWidth(right_col_widths[0])
                c_nom.setFixedHeight(data_row_h)

                thumb = ClickableThumbnail(g, self.aihub_scroll_content_right, scale=self.scale)
                thumb.setFixedWidth(right_col_widths[1])
                thumb.clicked.connect(self.pelican_clicked.emit)
                self._active_thumbnails.append(thumb)

                c_eff_multi = QLabel(html_eff)
                c_eff_multi.setFont(font_mono)
                c_eff_multi.setToolTip(eff_tip)
                c_eff_multi.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_eff_multi.setFixedWidth(right_col_widths[2])
                c_eff_multi.setFixedHeight(data_row_h)

                c_hit_multi = QLabel(html_hit)
                c_hit_multi.setFont(font_mono)
                c_hit_multi.setToolTip(hit_tip)
                c_hit_multi.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_hit_multi.setFixedWidth(right_col_widths[3])
                c_hit_multi.setFixedHeight(data_row_h)

                c_sr_multi = QLabel(html_sr)
                c_sr_multi.setFont(font_mono)
                c_sr_multi.setToolTip(sr_tip)
                c_sr_multi.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_sr_multi.setFixedWidth(right_col_widths[4])
                c_sr_multi.setFixedHeight(data_row_h)

                c_ref = QLabel()
                c_ref.setFont(font_mono)
                c_ref.setText(f"<span style='color: {ref_color}; font-weight: 600;'>{ref_cache_str}</span>")
                c_ref.setToolTip(f"官方参考缓存率基准:\n{ref_cache_str} ({g.get('code')})\n(来自官方 runtime_cache_1h 全网参考缓存基准)")
                c_ref.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                c_ref.setFixedWidth(right_col_widths[5])
                c_ref.setFixedHeight(data_row_h)

                self.aihub_grid_left.addWidget(c_dot, row_idx, 0, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_left.addWidget(c_candy, row_idx, 1, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_left.addWidget(c_name, row_idx, 2, Qt.AlignLeft | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(c_nom, row_idx, 0, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(thumb, row_idx, 1, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(c_eff_multi, row_idx, 2, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(c_hit_multi, row_idx, 3, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(c_sr_multi, row_idx, 4, Qt.AlignCenter | Qt.AlignVCenter)
                self.aihub_grid_right.addWidget(c_ref, row_idx, 5, Qt.AlignCenter | Qt.AlignVCenter)

                entry_dict.update({
                    "dot": c_dot, "candy": c_candy, "name": c_name, "nom": c_nom,
                    "thumb": thumb, "eff": c_eff_multi, "hit": c_hit_multi,
                    "sr": c_sr_multi, "ref": c_ref
                })
                self._aihub_rows.append(entry_dict)

        for extra in self._aihub_rows[len(monitored):]:
            for w in (extra["dot"], extra.get("candy"), extra["name"], extra["nom"], extra["thumb"], extra["eff"], extra["hit"], extra["sr"], extra["ref"]):
                if w:
                    w.hide()

