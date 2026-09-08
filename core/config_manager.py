"""
Configuration and State Management.
Handles loading, updating, saving config.json, and Windows autostart registry toggle.
"""

import os
import json
import winreg
from typing import Dict, Any

APP_NAME = "DesktopBatteryCodexWidget"
CONFIG_FILE_NAME = "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "window_pos": [100, 100],
    "is_mini_mode": False,
    "always_on_top": True,
    "lock_position": False,
    "auto_snap": True,
    "opacity": 0.95,
    "theme": "dark",
    "bt_interval_sec": 10,
    "codex_interval_sec": 60,
    "auth_file_path": "~/.codex/auth.json",
    "autostart": False,
}


class ConfigManager:
    """Manages application configurations and persistence."""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(config_dir, CONFIG_FILE_NAME)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load config from disk or return default."""
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    cfg.update(saved)
            except Exception as e:
                print(f"[ConfigManager] Load config failed: {e}")
        return cfg

    def save_config(self) -> bool:
        """Save current config to disk."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] Save config failed: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True):
        self.config[key] = value
        if auto_save:
            self.save_config()

    def set_autostart(self, enable: bool, exe_or_script_path: str) -> bool:
        """Toggle Windows Startup registry entry."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                # If script is py, use pythonw
                cmd = f'pythonw "{exe_or_script_path}"' if exe_or_script_path.endswith('.py') else f'"{exe_or_script_path}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            self.set("autostart", enable)
            return True
        except Exception as e:
            print(f"[ConfigManager] Autostart toggle error: {e}")
            return False

    def check_autostart_active(self) -> bool:
        """Check if registry key exists."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return bool(val)
        except FileNotFoundError:
            return False
        except Exception:
            return False
