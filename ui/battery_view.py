"""
Compact Bluetooth Device Battery View Component.
Only renders connected Bluetooth devices in clean, minimal rows.
"""

from typing import List, Dict, Any
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame
)
from PyQt5.QtCore import Qt


class DeviceBatteryItem(QFrame):
    """Single compact Bluetooth device battery card row."""
    
    def __init__(self, device_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setProperty("class", "CardSection")
        self.setFixedHeight(32)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        
        # 1. Icon
        self.icon_lbl = QLabel(device_data.get("icon", "📶"), self)
        self.icon_lbl.setStyleSheet("font-size: 13px;")
        self.icon_lbl.setFixedWidth(18)
        layout.addWidget(self.icon_lbl)
        
        # 2. Name & Mini Progress Bar
        mid_layout = QVBoxLayout()
        mid_layout.setSpacing(2)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.name_lbl = QLabel(device_data.get("name", "未知设备"), self)
        self.name_lbl.setProperty("class", "DeviceName")
        self.name_lbl.setToolTip(f"{device_data.get('raw_name', '')}\n类型: {device_data.get('type_name', '')}")
        
        metrics = self.name_lbl.fontMetrics()
        elided = metrics.elidedText(self.name_lbl.text(), Qt.ElideRight, 110)
        self.name_lbl.setText(elided)
        
        self.pbar = QProgressBar(self)
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.setRange(0, 100)
        bat_val = int(device_data.get("battery", 0))
        self.pbar.setValue(bat_val)
        
        color = device_data.get("status_color", "#10B981")
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
        
        mid_layout.addWidget(self.name_lbl)
        mid_layout.addWidget(self.pbar)
        layout.addLayout(mid_layout, 1)
        
        # 3. Battery percentage
        self.bat_lbl = QLabel(f"{bat_val}%", self)
        self.bat_lbl.setProperty("class", "BatteryPercent")
        self.bat_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.bat_lbl)


class BatteryView(QWidget):
    """Container view for connected Bluetooth devices."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)
        
        # Header
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(2, 0, 2, 0)
        
        self.title_lbl = QLabel("⚡ 蓝牙外设", self)
        self.title_lbl.setProperty("class", "SectionHeader")
        
        self.count_lbl = QLabel("0 已连", self)
        self.count_lbl.setProperty("class", "SubText")
        
        self.header_layout.addWidget(self.title_lbl)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.count_lbl)
        
        self.main_layout.addLayout(self.header_layout)
        
        # Device list container
        self.list_container = QWidget(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        
        self.main_layout.addWidget(self.list_container)
        
        # Empty placeholder
        self.empty_lbl = QLabel("无在线蓝牙设备", self)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color: #6B7280; font-size: 10px; padding: 6px;")
        self.empty_lbl.hide()
        self.main_layout.addWidget(self.empty_lbl)

    def update_devices(self, devices: List[Dict[str, Any]]):
        """Rebuild or update device items."""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        if not devices:
            self.empty_lbl.show()
            self.count_lbl.setText("0 已连")
            return
            
        self.empty_lbl.hide()
        self.count_lbl.setText(f"{len(devices)} 已连")
        
        for dev in devices:
            item_widget = DeviceBatteryItem(dev, self.list_container)
            self.list_layout.addWidget(item_widget)
