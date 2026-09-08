"""
Settings & Preferences Dialog.
Allows customizing refresh rates, opacity, autostart, UI scale, and auth file path.
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QSlider,
    QCheckBox, QLineEdit, QPushButton, QFileDialog, QMessageBox, QGroupBox, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from core.config_manager import ConfigManager
from core.codex_client import CodexUsageClient


class SettingsDialog(QDialog):
    """Settings Configuration Dialog."""
    
    settings_saved = pyqtSignal()
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("桌面悬浮插件 - 偏好设置")
        self.setFixedSize(360, 490)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #111827;
                color: #F3F4F6;
            }
            QGroupBox {
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
                color: #9CA3AF;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #E5E7EB;
                font-size: 11px;
            }
            QSpinBox, QLineEdit, QComboBox {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 4px;
                color: #F9FAFB;
                padding: 3px 6px;
                font-size: 11px;
            }
            QCheckBox {
                color: #E5E7EB;
                font-size: 11px;
                spacing: 6px;
            }
            QPushButton {
                background-color: #374151;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
            QPushButton#SaveBtn {
                background-color: #3B82F6;
            }
            QPushButton#SaveBtn:hover {
                background-color: #2563EB;
            }
        """)
        
        self.init_ui()
        self.load_values()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 10, 14, 14)
        
        # 1. Basic & Appearance
        grp_app = QGroupBox("外观与紧凑度", self)
        lay_app = QVBoxLayout(grp_app)
        lay_app.setSpacing(6)
        
        # Scale
        scale_lay = QHBoxLayout()
        scale_lbl = QLabel("界面尺寸缩放:", grp_app)
        self.combo_scale = QComboBox(grp_app)
        self.combo_scale.addItem("超紧凑 (80%)", 0.80)
        self.combo_scale.addItem("精简 (90%)", 0.90)
        self.combo_scale.addItem("标准 (100%)", 1.00)
        self.combo_scale.addItem("放大 (115%)", 1.15)
        scale_lay.addWidget(scale_lbl)
        scale_lay.addStretch()
        scale_lay.addWidget(self.combo_scale)
        lay_app.addLayout(scale_lay)
        
        # Opacity slider
        op_layout = QHBoxLayout()
        op_lbl = QLabel("窗口不透明度:", grp_app)
        self.op_val_lbl = QLabel("95%", grp_app)
        self.op_val_lbl.setStyleSheet("color: #60A5FA; font-weight: bold;")
        self.slider_opacity = QSlider(Qt.Horizontal, grp_app)
        self.slider_opacity.setRange(40, 100)
        self.slider_opacity.setValue(95)
        self.slider_opacity.valueChanged.connect(lambda v: self.op_val_lbl.setText(f"{v}%"))
        
        op_layout.addWidget(op_lbl)
        op_layout.addWidget(self.slider_opacity)
        op_layout.addWidget(self.op_val_lbl)
        lay_app.addLayout(op_layout)
        
        # Checkboxes
        self.chk_top = QCheckBox("总是窗口置顶 (Always on Top)", grp_app)
        self.chk_snap = QCheckBox("屏幕边缘自动吸附", grp_app)
        self.chk_only_conn = QCheckBox("只显示当前已连接设备 (推荐)", grp_app)
        self.chk_autostart = QCheckBox("开机自动启动", grp_app)
        lay_app.addWidget(self.chk_top)
        lay_app.addWidget(self.chk_snap)
        lay_app.addWidget(self.chk_only_conn)
        lay_app.addWidget(self.chk_autostart)
        
        layout.addWidget(grp_app)
        
        # 2. Refresh Intervals
        grp_int = QGroupBox("刷新频率", self)
        lay_int = QVBoxLayout(grp_int)
        lay_int.setSpacing(6)
        
        bt_int_lay = QHBoxLayout()
        bt_int_lbl = QLabel("蓝牙检测间隔 (秒):", grp_int)
        self.spin_bt_interval = QSpinBox(grp_int)
        self.spin_bt_interval.setRange(3, 60)
        self.spin_bt_interval.setValue(10)
        bt_int_lay.addWidget(bt_int_lbl)
        bt_int_lay.addStretch()
        bt_int_lay.addWidget(self.spin_bt_interval)
        lay_int.addLayout(bt_int_lay)
        
        cdx_int_lay = QHBoxLayout()
        cdx_int_lbl = QLabel("ChatGPT 额度查询间隔 (秒):", grp_int)
        self.spin_cdx_interval = QSpinBox(grp_int)
        self.spin_cdx_interval.setRange(20, 600)
        self.spin_cdx_interval.setValue(60)
        cdx_int_lay.addWidget(cdx_int_lbl)
        cdx_int_lay.addStretch()
        cdx_int_lay.addWidget(self.spin_cdx_interval)
        lay_int.addLayout(cdx_int_lay)
        
        layout.addWidget(grp_int)
        
        # 3. Auth Path & Test
        grp_auth = QGroupBox("ChatGPT 凭证配置", self)
        lay_auth = QVBoxLayout(grp_auth)
        lay_auth.setSpacing(6)
        
        path_lay = QHBoxLayout()
        self.edit_auth_path = QLineEdit(grp_auth)
        self.edit_auth_path.setPlaceholderText("~/.codex/auth.json")
        btn_browse = QPushButton("浏览...", grp_auth)
        btn_browse.clicked.connect(self.browse_auth_file)
        path_lay.addWidget(self.edit_auth_path)
        path_lay.addWidget(btn_browse)
        lay_auth.addLayout(path_lay)
        
        btn_test = QPushButton("🔍 测试凭据与消耗曲线", grp_auth)
        btn_test.clicked.connect(self.test_auth)
        lay_auth.addWidget(btn_test)
        
        layout.addWidget(grp_auth)
        layout.addStretch()
        
        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("取消", self)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存设置", self)
        btn_save.setObjectName("SaveBtn")
        btn_save.clicked.connect(self.save_values)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def load_values(self):
        self.slider_opacity.setValue(int(self.cfg.get("opacity", 0.95) * 100))
        self.chk_top.setChecked(self.cfg.get("always_on_top", True))
        self.chk_snap.setChecked(self.cfg.get("auto_snap", True))
        self.chk_only_conn.setChecked(self.cfg.get("only_connected", True))
        self.chk_autostart.setChecked(self.cfg.check_autostart_active())
        self.spin_bt_interval.setValue(self.cfg.get("bt_interval_sec", 10))
        self.spin_cdx_interval.setValue(self.cfg.get("codex_interval_sec", 60))
        self.edit_auth_path.setText(self.cfg.get("auth_file_path", "~/.codex/auth.json"))
        
        # Scale
        current_scale = self.cfg.get("scale", 1.0)
        idx = self.combo_scale.findData(current_scale)
        if idx >= 0:
            self.combo_scale.setCurrentIndex(idx)
        else:
            self.combo_scale.setCurrentIndex(2)

    def browse_auth_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 auth.json 凭证文件", os.path.expanduser("~/.codex"), "JSON Files (*.json)")
        if path:
            self.edit_auth_path.setText(path)

    def test_auth(self):
        path = self.edit_auth_path.text().strip()
        client = CodexUsageClient(path)
        res = client.fetch_usage(force=True)
        if res.get("success"):
            plan = res.get("plan_type", "")
            pw = res.get("primary_window", {}) or {}
            remain = pw.get("remaining_percent", 0)
            countdown = pw.get("reset_countdown", "")
            QMessageBox.information(
                self, "凭证测试成功",
                f"✅ 连接成功！\n"
                f"会员级别: {plan}\n"
                f"当前剩余用量: {remain}%\n"
                f"重置倒计时: {countdown}\n"
                f"账户: {res.get('email', '')}"
            )
        else:
            QMessageBox.warning(self, "凭证测试失败", f"❌ 无法连接: {res.get('error', '未知错误')}")

    def save_values(self):
        self.cfg.set("opacity", self.slider_opacity.value() / 100.0, auto_save=False)
        self.cfg.set("scale", self.combo_scale.currentData(), auto_save=False)
        self.cfg.set("always_on_top", self.chk_top.isChecked(), auto_save=False)
        self.cfg.set("auto_snap", self.chk_snap.isChecked(), auto_save=False)
        self.cfg.set("only_connected", self.chk_only_conn.isChecked(), auto_save=False)
        self.cfg.set("bt_interval_sec", self.spin_bt_interval.value(), auto_save=False)
        self.cfg.set("codex_interval_sec", self.spin_cdx_interval.value(), auto_save=False)
        self.cfg.set("auth_file_path", self.edit_auth_path.text().strip(), auto_save=False)
        
        main_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        self.cfg.set_autostart(self.chk_autostart.isChecked(), main_py_path)
        
        self.cfg.save_config()
        self.settings_saved.emit()
        self.accept()
