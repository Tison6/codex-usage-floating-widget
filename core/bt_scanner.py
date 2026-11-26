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

DEVPKEY_DeviceContainer_AlwaysShowDeviceAsConnected = DEVPROPKEY((ctypes.c_byte * 16)(*GUID_DEV.bytes_le), 101)

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
        return int.from_bytes(bytes(buf), "little", signed=proptype.value == 0x2)
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


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(name, wintypes.WORD) for name in
                ("year", "month", "weekday", "day", "hour", "minute", "second", "millisecond")]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("authenticated", wintypes.BOOL),
                ("remembered", wintypes.BOOL), ("unknown", wintypes.BOOL),
                ("connected", wintypes.BOOL), ("inquiry", wintypes.BOOL),
                ("timeout", ctypes.c_ubyte), ("radio", wintypes.HANDLE)]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("address", ctypes.c_ulonglong),
                ("device_class", wintypes.ULONG), ("connected", wintypes.BOOL),
                ("remembered", wintypes.BOOL), ("authenticated", wintypes.BOOL),
                ("last_seen", SYSTEMTIME), ("last_used", SYSTEMTIME),
                ("name", wintypes.WCHAR * 248)]


def _get_classic_connected_devices():
    """Read existing radio connections without starting a Bluetooth discovery scan."""
    result = {}
    api = ctypes.WinDLL("BluetoothAPIs.dll")
    api.BluetoothFindFirstDevice.argtypes = [ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS), ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
    api.BluetoothFindFirstDevice.restype = wintypes.HANDLE
    api.BluetoothFindNextDevice.argtypes = [wintypes.HANDLE, ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
    api.BluetoothFindNextDevice.restype = wintypes.BOOL
    api.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
    search = BLUETOOTH_DEVICE_SEARCH_PARAMS()
    search.size = ctypes.sizeof(search)
    search.connected = True
    device = BLUETOOTH_DEVICE_INFO()
    device.size = ctypes.sizeof(device)
    handle = api.BluetoothFindFirstDevice(ctypes.byref(search), ctypes.byref(device))
    if not handle:
        return result
    try:
        while True:
            if device.connected:
                result[f"{device.address:012X}"] = device.name
            if not api.BluetoothFindNextDevice(handle, ctypes.byref(device)):
                break
    finally:
        api.BluetoothFindDeviceClose(handle)
    return result


class BluetoothScanner:
    """High-performance Windows Bluetooth Device & Battery Scanner."""
    
    @staticmethod
    def get_connected_devices(only_connected: bool = True, include_standby: bool = False) -> List[Dict[str, Any]]:
        """
        Read physical Bluetooth devices, merging service nodes by MAC.
        Optionally keep paired input devices with a cached battery reading while asleep.
        """
        hdevinfo = setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
        if hdevinfo == -1 or hdevinfo == 0:
            return []
        
        devinfo_data = SP_DEVINFO_DATA()
        devinfo_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        
        try:
            classic_devices = _get_classic_connected_devices()
        except OSError:
            classic_devices = {}
        connected_macs = set(classic_devices)
        entries = []
        root_names = dict(classic_devices)
        standby_macs = set()
        index = 0
        try:
            while setupapi.SetupDiEnumDeviceInfo(hdevinfo, index, ctypes.byref(devinfo_data)):
                devinst = devinfo_data.DevInst
                inst_id = str(_get_devnode_property(devinst, DEVPKEY_Device_InstanceId) or "")
                mac = _extract_device_mac(inst_id)
                is_conn = _get_devnode_property(devinst, DEVPKEY_Device_IsConnected)
                if mac and is_conn is True:
                    connected_macs.add(mac)
                name = str(_get_devnode_property(devinst, DEVPKEY_Device_FriendlyName)
                           or _get_devnode_property(devinst, DEVPKEY_NAME) or "")
                battery = _get_devnode_property(devinst, DEVPKEY_Device_BatteryPercentage)
                if not isinstance(battery, int) or not 0 <= battery <= 100:
                    battery = None
                is_root = inst_id.upper().startswith(("BTHENUM\\DEV_", "BTHLE\\DEV_"))
                if is_root and mac and name:
                    root_names[mac] = name
                    if _get_devnode_property(devinst, DEVPKEY_DeviceContainer_AlwaysShowDeviceAsConnected) is True:
                        standby_macs.add(mac)
                if mac and (battery is not None or is_root):
                    entries.append({"name": name, "instance_id": inst_id, "mac": mac, "battery": battery,
                                    "is_charging": bool(_get_devnode_property(devinst, DEVPKEY_Device_IsCharging)),
                                    "is_connected": is_conn is True})
                index += 1
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(hdevinfo)

        by_mac = {mac: {"name": name, "instance_id": "", "mac": mac, "battery": None,
                        "is_charging": False, "is_connected": True}
                  for mac, name in classic_devices.items()}
        for entry in entries:
            active = entry["mac"] in connected_macs
            device_type = _guess_device_icon_and_type(
                _clean_device_name(root_names.get(entry["mac"]) or entry["name"]),
                entry["instance_id"],
            )["type"]
            standby = (
                entry["mac"] in standby_macs
                and not active
                and device_type in ("keyboard", "mouse", "stylus")
                and entry["battery"] is not None
            )
            if only_connected and not active and not (include_standby and standby):
                continue
            entry["is_connected"] = active
            entry["is_standby"] = standby
            previous = by_mac.get(entry["mac"])
            if previous is None or entry["battery"] is not None:
                by_mac[entry["mac"]] = entry

        devices = []
        for mac, entry in by_mac.items():
            raw_name = root_names.get(mac) or entry["name"]
            clean_name = _clean_device_name(raw_name)
            battery = entry["battery"]
            icon = _guess_device_icon_and_type(clean_name, entry["instance_id"])
            if battery is None:
                color, status = "#9CA3AF", "设备未提供电量"
            elif battery > 50:
                color, status = "#10B981", "良好"
            elif battery >= 20:
                color, status = "#F59E0B", "正常"
            else:
                color, status = "#EF4444", "低电量"
            if entry.get("is_standby"):
                status = "已配对，当前未连接或待机；电量为 Windows 最近读数"
            devices.append({**entry, "raw_name": raw_name, "name": clean_name,
                            **icon, "status_color": color, "status_text": status})
        devices.sort(key=lambda device: (device["battery"] is None,
                                         device["battery"] if device["battery"] is not None else 101,
                                         device["name"]))
        return devices


if __name__ == "__main__":
    scanner = BluetoothScanner()
    devs = scanner.get_connected_devices(only_connected=True)
    print(f"Connected devices ({len(devs)}):")
    for d in devs:
        print(f"  {d['name']}: {d['battery']}%")
