"""
Relay Stations Group & Provider Selection Dialogs.
Allows users to manually check and uncheck which Square groups/models and AIHub providers to monitor,
displaying live parameters (multiplier, cache rate, TTFT/latency, success rates) to make informed choices.
"""

from typing import List, Dict, Any, Set, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QCheckBox, QFrame,
    QGraphicsDropShadowEffect, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QCursor

from core.square_client import DEFAULT_SELECTED_GROUPS, DEFAULT_SELECTED_MODELS, DEFAULT_GROUP_MODELS
from core.aihub_client import DEFAULT_SELECTED_PROVIDERS

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
        self.group_model_combos: Dict[str, QComboBox] = {}

        self.init_window()
        self.init_ui()

    def init_window(self):
        self.setWindowTitle("Square API 监控项筛选")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(560, 520)

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
        title_lbl = QLabel("⚙️ 勾选 Square 监控项 (实时生效)")
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
        tabs.addTab(tab_groups, "1. 勾选关注分组 (含实时参数)")

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
        tip_lbl = QLabel("提示: 勾选分组将在主界面展示其速度、延迟与成功率")
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

        # Table Column Header
        h_row = QHBoxLayout()
        h_row.setContentsMargins(8, 2, 8, 2)
        h_g = QLabel("分组名称")
        h_g.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
        h_row.addWidget(h_g)
        h_row.addStretch()

        for title, w in [("关注模型", 115), ("倍率", 40), ("速度", 46), ("延迟", 44), ("成功率", 46)]:
            lbl = QLabel(title)
            lbl.setFixedWidth(w)
            lbl.setAlignment(Qt.AlignCenter if title in ["关注模型", "倍率", "成功率"] else Qt.AlignRight)
            lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
            h_row.addWidget(lbl)
        layout.addLayout(h_row)

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
        all_models = (self.square_client.cached_data or {}).get("all_models", [])
        mapping = self.square_client.get_group_models_mapping()
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
            r_lay.setSpacing(6)

            cb = QCheckBox(g_name)
            cb.setChecked(g_name in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            self.group_checkboxes[g_name] = cb
            r_lay.addWidget(cb)
            r_lay.addStretch()

            # Focus Model Selector
            combo = QComboBox()
            combo.setFixedWidth(115)
            combo.setFixedHeight(20)
            combo.setStyleSheet("""
                QComboBox {
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 3px;
                    color: #F1F5F9;
                    font-size: 9px;
                    padding: 0px 4px;
                }
                QComboBox QAbstractItemView {
                    background: #1E293B;
                    color: #F8FAFC;
                    selection-background-color: #3B82F6;
                    font-size: 9px;
                }
            """)
            models_to_use = all_models if all_models else [{"name": m, "display_name": m} for m in DEFAULT_SELECTED_MODELS]
            en_models = [m for m in models_to_use if g_name in m.get("enable_groups", [])]
            cand_models = en_models if en_models else models_to_use
            for m in cand_models:
                combo.addItem(m.get("display_name", m["name"]), m["name"])

            cur_focus = mapping.get(g_name, DEFAULT_GROUP_MODELS.get(g_name, "gpt-6-astra"))
            idx = combo.findData(cur_focus)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.group_model_combos[g_name] = combo
            r_lay.addWidget(combo)

            # Multiplier badge
            ratio_lbl = QLabel(g.get("ratio_str", "--"))
            ratio_lbl.setFixedWidth(40)
            ratio_lbl.setAlignment(Qt.AlignCenter)
            ratio_lbl.setStyleSheet("""
                background: rgba(59, 130, 246, 0.2);
                color: #60A5FA;
                border-radius: 3px;
                padding: 1px 3px;
                font-size: 9px;
                font-weight: 700;
            """)
            r_lay.addWidget(ratio_lbl)

            # Speed
            tps_lbl = QLabel(g.get("tps", "--"))
            tps_lbl.setFixedWidth(46)
            tps_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tps_lbl.setStyleSheet("font-size: 9px; color: #CBD5E1;")
            r_lay.addWidget(tps_lbl)

            # Latency
            lat_lbl = QLabel(g.get("latency", "--"))
            lat_lbl.setFixedWidth(44)
            lat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lat_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")
            r_lay.addWidget(lat_lbl)

            # Success rate
            sr_val = g.get("success_rate", 100.0)
            sr_lbl = QLabel(f"{sr_val:.1f}%")
            sr_lbl.setFixedWidth(46)
            sr_lbl.setAlignment(Qt.AlignCenter)
            sr_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #10B981;")
            r_lay.addWidget(sr_lbl)

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
        for g_name, combo in self.group_model_combos.items():
            cur_focus = DEFAULT_GROUP_MODELS.get(g_name)
            if cur_focus:
                idx = combo.findData(cur_focus)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def save_and_apply(self):
        selected_groups = [name for name, cb in self.group_checkboxes.items() if cb.isChecked()]
        selected_models = [name for name, cb in self.model_checkboxes.items() if cb.isChecked()]

        new_mapping = {}
        for g_name, combo in self.group_model_combos.items():
            new_mapping[g_name] = combo.currentData() or combo.currentText()

        self.square_client.set_selected_groups(selected_groups)
        self.square_client.set_selected_models(selected_models)
        self.square_client.set_group_models_mapping(new_mapping)

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


class AIHubFilterDialog(QDialog):
    """Modern dark-themed popup dialog for configuring AIHub monitored providers with live stats."""

    filters_changed = pyqtSignal()

    def __init__(self, aihub_client, parent=None):
        super().__init__(parent)
        self.aihub_client = aihub_client
        self.provider_checkboxes: Dict[str, QCheckBox] = {}
        self.provider_data_map: Dict[str, Dict[str, Any]] = {}

        self.init_window()
        self.init_ui()

    def init_window(self):
        self.setWindowTitle("AIHub 供应商监控项筛选")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(560, 520)

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
        title_lbl = QLabel("⚙️ 勾选 AIHub 监控供应商 (实时参数筛选)")
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

        # Subtitle & Action bar
        act_row = QHBoxLayout()
        tip_lbl = QLabel("查看各供应商实时倍率、缓存率与成功率，低成功率(<50%)已高亮标红")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_good = QPushButton("⭐ 推荐预设")
        btn_good.setFixedHeight(20)
        btn_good.setCursor(Qt.PointingHandCursor)
        btn_good.setStyleSheet("font-size: 10px; color: #34D399; background: transparent; border: none; font-weight: 600;")
        btn_good.setToolTip("自动勾选推荐监控的优质供应商")
        btn_good.clicked.connect(self.apply_good_preset)

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all(True))

        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all(False))

        act_row.addWidget(btn_good)
        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # Table Column Header
        h_row = QHBoxLayout()
        h_row.setContentsMargins(8, 2, 8, 2)
        h_prov = QLabel("供应商代码")
        h_prov.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
        h_row.addWidget(h_prov)
        h_row.addStretch()

        for title, w in [("真实倍率", 48), ("缓存率", 44), ("TTFT", 42), ("成功率", 56), ("实测图", 36)]:
            lbl = QLabel(title)
            lbl.setFixedWidth(w)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
            h_row.addWidget(lbl)
        layout.addLayout(h_row)

        # Scroll Area for Providers
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

        all_providers = (self.aihub_client.cached_data or {}).get("all_providers", [])
        cur_selected = set(self.aihub_client.get_selected_providers() or [])

        for p in all_providers:
            code = p["code"]
            self.provider_data_map[code] = p

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
            r_lay.setSpacing(6)

            cb = QCheckBox(code)
            cb.setChecked(code in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            cb.stateChanged.connect(self.update_count_label)
            self.provider_checkboxes[code] = cb
            r_lay.addWidget(cb)
            r_lay.addStretch()

            # Multiplier badge (shows real effective multiplier, tooltip shows both)
            eff_mult = p.get("effective_multiplier_str") or p.get("multiplier_str", "--")
            nom_mult = p.get("multiplier_str", "--")
            mult_lbl = QLabel(eff_mult)
            mult_lbl.setFixedWidth(48)
            mult_lbl.setAlignment(Qt.AlignCenter)
            mult_lbl.setToolTip(f"真实倍率: {eff_mult} (含实际缓存计费折算)\n名义倍率: {nom_mult}")
            mult_lbl.setStyleSheet("""
                background: rgba(16, 185, 129, 0.18);
                color: #34D399;
                border-radius: 3px;
                padding: 1px 3px;
                font-size: 9px;
                font-weight: 700;
            """)
            r_lay.addWidget(mult_lbl)

            # Cache hit rate
            cache_lbl = QLabel(p.get("cache_hit_rate", "-"))
            cache_lbl.setFixedWidth(44)
            cache_lbl.setAlignment(Qt.AlignCenter)
            cache_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")
            r_lay.addWidget(cache_lbl)

            # TTFT
            ttft_lbl = QLabel(p.get("ttft_str", "--"))
            ttft_lbl.setFixedWidth(42)
            ttft_lbl.setAlignment(Qt.AlignCenter)
            ttft_lbl.setStyleSheet("font-size: 9px; color: #64748B;")
            r_lay.addWidget(ttft_lbl)

            # Success rate with warning color if bad
            sr_val = float(p.get("success_rate", 100.0))
            sr_text = p.get("success_rate_str", "--")
            sr_lbl = QLabel()
            sr_lbl.setFixedWidth(56)
            sr_lbl.setAlignment(Qt.AlignCenter)

            if sr_val < 50.0:
                sr_lbl.setText(f"⚠️ {sr_text}")
                sr_lbl.setStyleSheet("""
                    background: rgba(239, 68, 68, 0.2);
                    border: 1px solid rgba(239, 68, 68, 0.4);
                    color: #EF4444;
                    border-radius: 3px;
                    padding: 1px 2px;
                    font-size: 8px;
                    font-weight: 700;
                """)
                sr_lbl.setToolTip(f"该供应商成功率仅 {sr_val:.1f}%，极不稳定，建议取消勾选！")
            elif sr_val < 90.0:
                sr_lbl.setText(sr_text)
                sr_lbl.setStyleSheet("font-size: 9px; font-weight: 600; color: #F59E0B;")
            else:
                sr_lbl.setText(sr_text)
                sr_lbl.setStyleSheet("font-size: 9px; font-weight: 600; color: #10B981;")

            r_lay.addWidget(sr_lbl)

            # Has image indicator
            img_lbl = QLabel("📷" if p.get("has_image") else "-")
            img_lbl.setFixedWidth(36)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("font-size: 10px; color: #10B981;" if p.get("has_image") else "font-size: 9px; color: #475569;")
            r_lay.addWidget(img_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Footer
        footer = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        self.update_count_label()
        footer.addWidget(self.count_lbl)
        footer.addStretch()

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
        footer.addWidget(btn_save)
        layout.addLayout(footer)

        root.addWidget(container)

    def update_count_label(self):
        checked = sum(1 for cb in self.provider_checkboxes.values() if cb.isChecked())
        total = len(self.provider_checkboxes)
        self.count_lbl.setText(f"已勾选: {checked} / 总计 {total} 个供应商")

    def toggle_all(self, checked: bool):
        for cb in self.provider_checkboxes.values():
            cb.setChecked(checked)
        self.update_count_label()

    def apply_good_preset(self):
        for code, cb in self.provider_checkboxes.items():
            cb.setChecked(code in DEFAULT_SELECTED_PROVIDERS)
        self.update_count_label()

    def save_and_apply(self):
        selected_codes = [code for code, cb in self.provider_checkboxes.items() if cb.isChecked()]
        self.aihub_client.set_selected_providers(selected_codes)

        # Force re-computation of monitored rows
        self.aihub_client.fetch_data(force=True)
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
