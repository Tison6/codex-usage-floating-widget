"""UI package for Desktop Floating Widget."""
from .floating_widget import FloatingWidget
from .battery_view import BatteryView
from .codex_view import CodexQuotaView
from .sparkline_widget import QuotaSparklineWidget
from .status_light import CodexStatusLight
from .settings_dialog import SettingsDialog
from .tray_manager import TrayManager

__all__ = [
    "FloatingWidget", "BatteryView", "CodexQuotaView",
    "QuotaSparklineWidget", "CodexStatusLight", "SettingsDialog", "TrayManager"
]
