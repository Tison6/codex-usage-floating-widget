"""
Square API Group and Model Selection Dialog.
Allows users to manually check and uncheck which groups and models they want to monitor.
"""

from typing import List, Dict, Any, Set
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QCheckBox, QFrame,
    QLineEdit, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QCursor

from core.square_client import DEFAULT_SELECTED_GROUPS, DEFAULT_SELECTED_MODELS

SCROLL_STYLE = """
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: rgba(255, 255, 255, 0.03);
        width: 5px;
        margin: 0px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.2);
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

CHECKBOX_STYLE = """
    QCheckBox {
        color: #E2E8F0;
        font-size: 11px;
        font-weight: 600;
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 3px;
        background: rgba(255, 255, 255, 0.05);
    }
    QCheckBox::indicator:hover {
        border-color: #38BDF8;
        background: rgba(56, 189, 248, 0.1);
    }
    QCheckBox::indicator:checked {
        background: #10B981;
        border-color: #10B981;
    }
"""


class SquareFilterDialog(QDialog):
    """Modern dark-themed popup dialog for configuring Square monitored groups and models."""

    filters_changed = pyqtSignal()

    def __init__(self, square_client, parent=None):
        super().__init__(parent)
        self.square_client = square_client
        self.group_checkboxes: Dict[str, QCheckBox] = {}
        self.model_checkboxes: Dict[str, QCheckBox] = {}

        self.init_window()
        self.init_ui()

    def init_window(self):
        self.setWindowTitle("Square API 监控项筛选")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(540, 520)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        container = QWidget(self)
        container.setObjectName("FilterContainer")
        container.setStyleSheet("""
            QWidget#FilterContainer {
                background-color: rgba(20, 24, 33, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. Header Bar
        header = QHBoxLayout()
        title_lbl = QLabel("⚙️ 勾选监控的分组与模型 (实时生效)")
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

        # 2. Tabs: Groups vs Models
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                background: rgba(15, 18, 26, 0.6);
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(59, 130, 246, 0.25);
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-bottom: none;
                color: #60A5FA;
            }
        """)

        # Tab 1: Groups Tab
        tab_groups = QWidget()
        self.init_groups_tab(tab_groups)
        tabs.addTab(tab_groups, "1. 勾选关注分组")

        # Tab 2: Models Tab
        tab_models = QWidget()
        self.init_models_tab(tab_models)
        tabs.addTab(tab_models, "2. 勾选关注模型")

        layout.addWidget(tabs, 1)

        # 3. Footer Bar with Quick Actions and Save
        footer = QHBoxLayout()
        btn_preset = QPushButton("推荐预设")
        btn_preset.setCursor(Qt.PointingHandCursor)
        btn_preset.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                color: #60A5FA;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.25);
            }
        """)
        btn_preset.clicked.connect(self.apply_recommended_preset)

        btn_save = QPushButton("保存并应用")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 4px 16px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        btn_save.clicked.connect(self.save_and_apply)

        footer.addWidget(btn_preset)
        footer.addStretch()
        footer.addWidget(btn_save)
        layout.addLayout(footer)

        root.addWidget(container)

    def init_groups_tab(self, parent_widget: QWidget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Actions row
        act_row = QHBoxLayout()
        tip_lbl = QLabel("提示: 勾选的分组将在中转站主界面展示其实时倍率与说明")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all_groups(True))
        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all_groups(False))

        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(4)

        all_groups = (self.square_client.cached_data or {}).get("all_groups", [])
        cur_selected = set(self.square_client.get_selected_groups())

        if not all_groups:
            all_groups = [{"name": g, "ratio_str": "--", "desc": ""} for g in DEFAULT_SELECTED_GROUPS]

        for g in all_groups:
            g_name = g["name"]
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                }
                QFrame:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(6, 4, 6, 4)

            cb = QCheckBox(g_name)
            cb.setChecked(g_name in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            self.group_checkboxes[g_name] = cb
            r_lay.addWidget(cb)

            ratio_lbl = QLabel(g.get("ratio_str", ""))
            ratio_lbl.setStyleSheet("""
                background: rgba(59, 130, 246, 0.2);
                color: #60A5FA;
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 9px;
                font-weight: 700;
            """)
            r_lay.addWidget(ratio_lbl)

            r_lay.addStretch()

            desc_lbl = QLabel(g.get("desc", ""))
            desc_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
            r_lay.addWidget(desc_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def init_models_tab(self, parent_widget: QWidget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Actions row
        act_row = QHBoxLayout()
        tip_lbl = QLabel("提示: 勾选的模型将自动映射并在所属分组下列出")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all_models(True))
        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all_models(False))

        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(4)

        all_models = (self.square_client.cached_data or {}).get("all_models", [])
        cur_selected = set(self.square_client.get_selected_models())

        if not all_models:
            all_models = [{"name": m, "display_name": m, "enable_groups": []} for m in DEFAULT_SELECTED_MODELS]

        for m in all_models:
            m_name = m["name"]
            d_name = m.get("display_name", m_name)
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                }
                QFrame:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(6, 4, 6, 4)

            cb = QCheckBox(f"{d_name} ({m_name})")
            cb.setChecked(m_name in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            self.model_checkboxes[m_name] = cb
            r_lay.addWidget(cb)
            r_lay.addStretch()

            eg_count = len(m.get("enable_groups", []))
            cnt_lbl = QLabel(f"支持 {eg_count} 个分组")
            cnt_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
            r_lay.addWidget(cnt_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def toggle_all_groups(self, checked: bool):
        for cb in self.group_checkboxes.values():
            cb.setChecked(checked)

    def toggle_all_models(self, checked: bool):
        for cb in self.model_checkboxes.values():
            cb.setChecked(checked)

    def apply_recommended_preset(self):
        for name, cb in self.group_checkboxes.items():
            cb.setChecked(name in DEFAULT_SELECTED_GROUPS)
        for name, cb in self.model_checkboxes.items():
            cb.setChecked(name in DEFAULT_SELECTED_MODELS)

    def save_and_apply(self):
        selected_groups = [name for name, cb in self.group_checkboxes.items() if cb.isChecked()]
        selected_models = [name for name, cb in self.model_checkboxes.items() if cb.isChecked()]

        self.square_client.set_selected_groups(selected_groups)
        self.square_client.set_selected_models(selected_models)

        # Force re-computation of monitored rows
        self.square_client.fetch_data(force=True)
        self.filters_changed.emit()
        self.close()

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
