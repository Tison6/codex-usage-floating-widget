"""
Pelican (鹈鹕) Test Image Viewer Dialog.
Displays the latest 5 model detection test images with timestamps and zoom/preview.
"""

import os
from typing import List, Dict, Any
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QColor, QFont, QCursor


class PelicanViewerDialog(QDialog):
    """Modern dark-themed popup dialog for inspecting the latest 5 Pelican test images."""

    def __init__(self, pelican_items: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.pelican_items = pelican_items or []
        self.current_idx = 0
        self.thumb_buttons: List[QPushButton] = []
        
        self.init_window()
        self.init_ui()
        if self.pelican_items:
            self.display_item(0)

    def init_window(self):
        self.setWindowTitle("AIHub 鹈鹕 (Pelican) 模型检测实测图")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(720, 560)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        # Main background container with rounded corners and border
        container = QWidget(self)
        container.setObjectName("PelicanContainer")
        container.setStyleSheet("""
            QWidget#PelicanContainer {
                background-color: rgba(20, 24, 33, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # 1. Header Bar
        header = QHBoxLayout()
        op_name = self.pelican_items[0].get("model_code", "同运营商") if self.pelican_items else "同运营商"
        title_lbl = QLabel(f"📷 鹈鹕 (Pelican) 实测图 - 【运营商: {op_name}】历史 5 次检测")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9;")
        
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

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(btn_close)
        layout.addLayout(header)

        # 2. Thumbnail / Navigation Row
        thumb_bar = QHBoxLayout()
        thumb_bar.setSpacing(8)

        for i, item in enumerate(self.pelican_items):
            time_str = item.get("published_at_str", f"图 #{i+1}")
            model = item.get("model_code", "AIHub")
            btn = QPushButton(f"#{i+1} {model}\n{time_str}")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 10px;
                    text-align: center;
                }
                QPushButton:hover {
                    background: rgba(59, 130, 246, 0.15);
                    border-color: rgba(59, 130, 246, 0.4);
                    color: #93C5FD;
                }
                QPushButton:checked {
                    background: rgba(16, 185, 129, 0.2);
                    border-color: #10B981;
                    color: #34D399;
                    font-weight: 700;
                }
            """)
            btn.clicked.connect(lambda checked, idx=i: self.display_item(idx))
            self.thumb_buttons.append(btn)
            thumb_bar.addWidget(btn)

        layout.addLayout(thumb_bar)

        # 3. Large Image Display Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                background: rgba(10, 12, 16, 0.8);
            }
        """)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("padding: 8px;")
        self.scroll_area.setWidget(self.img_label)
        layout.addWidget(self.scroll_area, 1)

        # 4. Footer Information
        self.footer_lbl = QLabel()
        self.footer_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(self.footer_lbl)

        root.addWidget(container)

    def display_item(self, index: int):
        if not (0 <= index < len(self.pelican_items)):
            return
        
        self.current_idx = index
        for i, btn in enumerate(self.thumb_buttons):
            btn.setChecked(i == index)

        item = self.pelican_items[index]
        local_path = item.get("local_path", "")
        time_str = item.get("published_at_str", "--")
        model = item.get("model_code", "未知")
        url = item.get("url", "")

        if local_path and os.path.exists(local_path):
            pixmap = QPixmap(local_path)
            if not pixmap.isNull():
                # Scale smoothly to fit viewer
                scaled = pixmap.scaled(
                    QSize(660, 380),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.img_label.setPixmap(scaled)
            else:
                self.img_label.setText("⚠️ 图片解析失败")
        else:
            self.img_label.setText("⏳ 正在下载实测图片...")

        self.footer_lbl.setText(
            f"模型分组: {model}  |  检测时间: {time_str}  |  原始链接: {url[:55]}..."
        )

    # Support ESC key to close
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # Support drag to move dialog
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
