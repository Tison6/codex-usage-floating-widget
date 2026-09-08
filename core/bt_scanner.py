"""
Windows SetupAPI Bluetooth Battery Scanner.
Reads battery percentages and connection status directly from Windows PnP properties
via ctypes without external dependencies or slow subprocesses.
Uses MAC address resolution to accurately match both BLE and Classic Hands-Free/Audio devices.
"""

import ctypes
from ctypes import wintypes
import uuid
import re
from typing import List, Dict, Any, Optional

# Ctypes structures for SetupAPI
class DEVPROPKEY(ctypes.Structure):
    _fields_ = [
        ("fmtid", ctypes.c_byte * 16),
        ("pid", wintypes.ULONG)
    ]

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8)
    ]

class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p)
    ]

# SetupAPI / CfgMgr32 DLL references
cfgmgr32 = ctypes.windll.cfgmgr32
setupapi = ctypes.windll.setupapi

setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

# Property GUIDs
GUID_BATTERY = uuid.UUID("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}")
DEVPKEY_Device_BatteryPercentage = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_BATTERY.bytes_le), 2)
DEVPKEY_Device_IsCharging = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_BATTERY.bytes_le), 3)

GUID_NAME = uuid.UUID("{B725F130-47EF-101A-A5F1-02608C9EEBAC}")
DEVPKEY_NAME = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_NAME.bytes_le), 10)

GUID_FRIENDLY = uuid.UUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}")
DEVPKEY_Device_FriendlyName = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_FRIENDLY.bytes_le), 14)

GUID_DEV = uuid.UUID("{78C34FC8-104A-4ACA-9EA4-524D52996E57}")
DEVPKEY_Device_InstanceId = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_DEV.bytes_le), 256)

GUID_CONN = uuid.UUID("{83DA6326-97A6-4088-9453-A1923F573B29}")
DEVPKEY_Device_IsConnected = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_CONN.bytes_le), 15)

DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004


def _get_devnode_property(devinst: int, propkey: DEVPROPKEY) -> Any:
    """Retrieve a property value from a DevNode handle."""
    proptype = wintypes.ULONG()
    buf_size = wintypes.ULONG(0)
    
    res = cfgmgr32.CM_Get_DevNode_PropertyW(
        devinst, ctypes.byref(propkey), ctypes.byref(proptype),
        None, ctypes.byref(buf_size), 0
    )
    if buf_size.value == 0:
        return None
    
    buf = (ctypes.c_byte * buf_size.value)()
    res = cfgmgr32.CM_Get_DevNode_PropertyW(
        devinst, ctypes.byref(propkey), ctypes.byref(proptype),
        buf, ctypes.byref(buf_size), 0
    )
    if res != 0:
        return None
    
    if proptype.value in (0x2, 0x3, 0x7):  # INT8, UINT8, UINT32
        return buf[0]
    elif proptype.value == 0x11:  # BOOLEAN
        return bool(buf[0])
    elif proptype.value == 0x12:  # STRING (Unicode)
        return ctypes.wstring_at(buf)
    return list(buf)


def _extract_device_mac(inst_id: str) -> str:
    """Extract 12-hex-digit Bluetooth MAC address from instance ID."""
    m = re.search(r"DEV_([0-9A-Fa-f]{12})", inst_id, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m2 = re.search(r"&([0-9A-Fa-f]{12})_", inst_id, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    m3 = re.search(r"&([0-9A-Fa-f]{12})$", inst_id, re.IGNORECASE)
    if m3:
        return m3.group(1).upper()
    return ""


def _clean_device_name(raw_name: str) -> str:
    """Strip Windows internal driver suffixes like 'Hands-Free AG', 'Avrcp', etc."""
    if not raw_name:
        return "未知蓝牙设备"
    
    name = raw_name.strip()
    patterns = [
        r"\s+Hands-Free\s+AG.*$",
        r"\s+Hands-Free\s+HF.*$",
        r"\s+Avrcp\s+.*$",
        r"\s+A2DP\s+.*$",
        r"\s+Stereo$",
        r"\s+Audio$",
        r"\s+Bluetooth\s+Device$",
    ]
    for pat in patterns:
        name = re.sub(pat, "", name, flags=re.IGNORECASE).strip()
    return name or raw_name


def _guess_device_icon_and_type(name: str, instance_id: str) -> Dict[str, str]:
    """Detect device category and assign corresponding emoji and category key."""
    name_lower = name.lower()
    inst_lower = instance_id.lower()
    
    if any(k in name_lower for k in ["keyboard", "keychron", "lofree", "nuphy", "flow84", "kbd", "ikbc", "filco", "anne", "ducky"]):
        return {"icon": "⌨️", "type": "keyboard", "type_name": "键盘"}
    elif any(k in name_lower for k in ["mouse", "mx master", "anywhere", "g502", "g304", "trackball", "touchpad", "magic mouse"]):
        return {"icon": "🖱️", "type": "mouse", "type_name": "鼠标"}
    elif any(k in name_lower for k in ["mic", "microphone", "dji mic", "wireless mic", "rode"]):
        return {"icon": "🎙️", "type": "mic", "type_name": "麦克风"}
    elif any(k in name_lower for k in ["buds", "earbuds", "freebuds", "airpods", "wh-1000", "wf-1000", "headphone", "headset", "earphone", "qc35", "qc45", "linkbuds"]):
        return {"icon": "🎧", "type": "headset", "type_name": "耳机"}
    elif any(k in name_lower for k in ["speaker", "soundbar", "flip", "charge", "boom", "jbl", "marshall"]):
        return {"icon": "🔊", "type": "speaker", "type_name": "音箱"}
    elif any(k in name_lower for k in ["iphone", "ipad", "android", "phone"]):
        return {"icon": "📱", "type": "phone", "type_name": "手机"}
    elif any(k in name_lower for k in ["watch", "band"]):
        return {"icon": "⌚", "type": "watch", "type_name": "手表"}
    elif any(k in name_lower for k in ["pen", "stylus"]):
        return {"icon": "✏️", "type": "stylus", "type_name": "手写笔"}
    
    if "bthle" in inst_lower:
        return {"icon": "📶", "type": "ble_device", "type_name": "蓝牙外设"}
    return {"icon": "📶", "type": "bluetooth", "type_name": "蓝牙设备"}


class BluetoothScanner:
    """High-performance Windows Bluetooth Device & Battery Scanner."""
    
    @staticmethod
    def get_connected_devices(only_connected: bool = True) -> List[Dict[str, Any]]:
        """
        Scan Bluetooth devices that report battery percentage.
        By default, strictly filters for currently connected devices only.
        """
        hdevinfo = setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
        if hdevinfo == -1 or hdevinfo == 0:
            return []
        
        devinfo_data = SP_DEVINFO_DATA()
        devinfo_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        
        connected_macs = set()
        raw_battery_entries = []
        
        index = 0
        while setupapi.SetupDiEnumDeviceInfo(hdevinfo, index, ctypes.byref(devinfo_data)):
            devinst = devinfo_data.DevInst
            inst_id = str(_get_devnode_property(devinst, DEVPKEY_Device_InstanceId) or "")
            is_conn = _get_devnode_property(devinst, DEVPKEY_Device_IsConnected)
            name = str(_get_devnode_property(devinst, DEVPKEY_Device_FriendlyName) or _get_devnode_property(devinst, DEVPKEY_NAME) or "")
            
            mac = _extract_device_mac(inst_id)
            if mac and is_conn is True:
                connected_macs.add(mac)
                
            bat = _get_devnode_property(devinst, DEVPKEY_Device_BatteryPercentage)
            if bat is not None and isinstance(bat, int) and 0 <= bat <= 100:
                is_charging = bool(_get_devnode_property(devinst, DEVPKEY_Device_IsCharging) or False)
                raw_battery_entries.append({
                    "devinst": devinst,
                    "name": name,
                    "inst_id": inst_id,
                    "bat": bat,
                    "is_charging": is_charging,
                    "is_conn": is_conn,
                    "mac": mac,
                })
            index += 1
            
        setupapi.SetupDiDestroyDeviceInfoList(hdevinfo)
        
        devices = []
        seen_names = set()
        
        for entry in raw_battery_entries:
            mac = entry["mac"]
            is_conn = entry["is_conn"]
            
            # Connected condition: direct is_conn is True OR MAC address is connected
            is_active = (is_conn is True) or (mac in connected_macs)
            if only_connected and not is_active:
                continue
                
            raw_name = entry["name"]
            clean_name = _clean_device_name(raw_name)
            
            # Filter out raw internal cryptographic GUID devices
            if len(clean_name) > 20 and "/" in clean_name and not any(k in clean_name.lower() for k in ["key", "mouse", "buds", "mic"]):
                continue
                
            if clean_name in seen_names:
                continue
            seen_names.add(clean_name)
            
            bat = entry["bat"]
            icon_info = _guess_device_icon_and_type(clean_name, entry["inst_id"])
            
            if bat > 50:
                status_color = "#10B981"  # Green
                status_text = "良好"
            elif bat >= 20:
                status_color = "#F59E0B"  # Amber
                status_text = "正常"
            else:
                status_color = "#EF4444"  # Red
                status_text = "低电量"
                
            devices.append({
                "raw_name": raw_name,
                "name": clean_name,
                "battery": bat,
                "is_charging": entry["is_charging"],
                "is_connected": True,
                "icon": icon_info["icon"],
                "type": icon_info["type"],
                "type_name": icon_info["type_name"],
                "status_color": status_color,
                "status_text": status_text,
                "instance_id": entry["inst_id"],
            })
            
        # Sort by lowest battery first
        devices.sort(key=lambda x: x["battery"])
        return devices


if __name__ == "__main__":
    scanner = BluetoothScanner()
    devs = scanner.get_connected_devices(only_connected=True)
    print(f"Connected devices ({len(devs)}):")
    for d in devs:
        print(f"  {d['name']}: {d['battery']}%")
