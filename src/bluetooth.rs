use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use windows::core::GUID;
use windows::Win32::Foundation::{BOOL, HANDLE, HWND};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BluetoothDevice {
    pub name: String,
    pub battery: i32,
    pub is_connected: bool,
    pub is_charging: bool,
    pub icon: String,
}

#[repr(C)]
pub struct DEVPROPKEY {
    pub fmtid: GUID,
    pub pid: u32,
}

#[repr(C)]
pub struct SP_DEVINFO_DATA {
    pub cb_size: u32,
    pub class_guid: GUID,
    pub dev_inst: u32,
    pub reserved: usize,
}

#[link(name = "setupapi")]
extern "system" {
    fn SetupDiGetClassDevsW(
        class_guid: *const GUID,
        enumerator: *const u16,
        hwnd_parent: HWND,
        flags: u32,
    ) -> HANDLE;
    fn SetupDiEnumDeviceInfo(
        dev_info_set: HANDLE,
        member_index: u32,
        devinfo_data: *mut SP_DEVINFO_DATA,
    ) -> BOOL;
    fn SetupDiDestroyDeviceInfoList(dev_info_set: HANDLE) -> BOOL;
}

#[link(name = "cfgmgr32")]
extern "system" {
    fn CM_Get_DevNode_PropertyW(
        dn_dev_node: u32,
        property_key: *const DEVPROPKEY,
        property_type: *mut u32,
        property_buffer: *mut u8,
        property_buffer_size: *mut u32,
        ul_flags: u32,
    ) -> u32;
}

const DIGCF_PRESENT: u32 = 0x00000002;
const DIGCF_ALLCLASSES: u32 = 0x00000004;

// {104EA319-6EE2-4701-BD47-8DDBF425BBE5}
const GUID_BATTERY: GUID = GUID::from_u128(0x104EA319_6EE2_4701_BD47_8DDBF425BBE5);
const DEVPKEY_DEVICE_BATTERY_PERCENTAGE: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_BATTERY, pid: 2 };
const DEVPKEY_DEVICE_IS_CHARGING: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_BATTERY, pid: 3 };

// {B725F130-47EF-101A-A5F1-02608C9EEBAC}
const GUID_NAME: GUID = GUID::from_u128(0xB725F130_47EF_101A_A5F1_02608C9EEBAC);
const DEVPKEY_NAME: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_NAME, pid: 10 };

// {A45C254E-DF1C-4EFD-8020-67D146A850E0}
const GUID_FRIENDLY: GUID = GUID::from_u128(0xA45C254E_DF1C_4EFD_8020_67D146A850E0);
const DEVPKEY_DEVICE_FRIENDLY_NAME: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_FRIENDLY, pid: 14 };

// {78C34FC8-104A-4ACA-9EA4-524D52996E57}
const GUID_DEV: GUID = GUID::from_u128(0x78C34FC8_104A_4ACA_9EA4_524D52996E57);
const DEVPKEY_DEVICE_INSTANCE_ID: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_DEV, pid: 256 };

// {83DA6326-97A6-4088-9453-A1923F573B29}
const GUID_CONN: GUID = GUID::from_u128(0x83DA6326_97A6_4088_9453_A1923F573B29);
const DEVPKEY_DEVICE_IS_CONNECTED: DEVPROPKEY = DEVPROPKEY { fmtid: GUID_CONN, pid: 15 };

unsafe fn get_devnode_property(devinst: u32, key: &DEVPROPKEY) -> Option<(u32, Vec<u8>)> {
    let mut proptype = 0u32;
    let mut buf_size = 0u32;
    let _ = CM_Get_DevNode_PropertyW(
        devinst,
        key,
        &mut proptype,
        std::ptr::null_mut(),
        &mut buf_size,
        0,
    );
    if buf_size == 0 {
        return None;
    }
    let mut buf = vec![0u8; buf_size as usize];
    let _res = CM_Get_DevNode_PropertyW(
        devinst,
        key,
        &mut proptype,
        buf.as_mut_ptr(),
        &mut buf_size,
        0,
    );
    if _res == 0 {
        Some((proptype, buf))
    } else {
        None
    }
}

unsafe fn get_devnode_property_u8(devinst: u32, key: &DEVPROPKEY) -> Option<u8> {
    if let Some((_ptype, buf)) = get_devnode_property(devinst, key) {
        if !buf.is_empty() {
            return Some(buf[0]);
        }
    }
    None
}

unsafe fn get_devnode_property_bool(devinst: u32, key: &DEVPROPKEY) -> Option<bool> {
    if let Some((_ptype, buf)) = get_devnode_property(devinst, key) {
        if !buf.is_empty() {
            return Some(buf[0] != 0);
        }
    }
    None
}

unsafe fn get_devnode_property_string(devinst: u32, key: &DEVPROPKEY) -> Option<String> {
    if let Some((proptype, buf)) = get_devnode_property(devinst, key) {
        if proptype == 0x12 && buf.len() >= 2 {
            let u16_slice: &[u16] = std::slice::from_raw_parts(
                buf.as_ptr() as *const u16,
                buf.len() / 2,
            );
            let s = String::from_utf16_lossy(u16_slice)
                .trim_matches('\0')
                .to_string();
            return Some(s);
        }
    }
    None
}

fn extract_device_mac(inst_id: &str) -> Option<String> {
    let upper = inst_id.to_uppercase();
    if let Some(pos) = upper.find("DEV_") {
        let sub = &upper[pos + 4..];
        if sub.len() >= 12 && sub[..12].chars().all(|c| c.is_ascii_hexdigit()) {
            return Some(sub[..12].to_string());
        }
    }
    if let Some(pos) = upper.find('&') {
        let sub = &upper[pos + 1..];
        if sub.len() >= 12 && sub[..12].chars().all(|c| c.is_ascii_hexdigit()) {
            return Some(sub[..12].to_string());
        }
    }
    None
}

fn clean_device_name(raw: &str) -> String {
    let mut name = raw.trim().to_string();
    let suffixes = [
        " Hands-Free AG", " Hands-Free HF", " Avrcp", " A2DP", " Stereo", " Audio", " Bluetooth Device",
    ];
    for s in suffixes {
        if let Some(pos) = name.to_lowercase().rfind(&s.to_lowercase()) {
            name.truncate(pos);
            name = name.trim().to_string();
        }
    }
    if name.is_empty() {
        "未知蓝牙设备".to_string()
    } else {
        name
    }
}

fn guess_device_icon(name: &str, inst_id: &str) -> &'static str {
    let lower = name.to_lowercase();
    let inst_lower = inst_id.to_lowercase();
    if ["keyboard", "keychron", "lofree", "nuphy", "flow84", "kbd", "ikbc", "filco", "anne", "ducky"]
        .iter().any(|k| lower.contains(k)) {
        "⌨️"
    } else if ["mouse", "mx master", "anywhere", "g502", "g304", "trackball", "touchpad", "magic mouse"]
        .iter().any(|k| lower.contains(k)) {
        "🖱️"
    } else if ["mic", "microphone", "dji mic", "wireless mic", "rode"]
        .iter().any(|k| lower.contains(k)) {
        "🎙️"
    } else if ["buds", "earbuds", "freebuds", "airpods", "wh-1000", "wf-1000", "headphone", "headset", "earphone", "qc35", "qc45", "linkbuds"]
        .iter().any(|k| lower.contains(k)) {
        "🎧"
    } else if ["speaker", "soundbar", "flip", "charge", "boom", "jbl", "marshall"]
        .iter().any(|k| lower.contains(k)) {
        "🔊"
    } else if ["iphone", "ipad", "android", "phone"]
        .iter().any(|k| lower.contains(k)) {
        "📱"
    } else if ["watch", "band"].iter().any(|k| lower.contains(k)) {
        "⌚"
    } else if ["pen", "stylus"].iter().any(|k| lower.contains(k)) {
        "✏️"
    } else if inst_lower.contains("bthle") {
        "📶"
    } else {
        "📶"
    }
}

pub struct BluetoothScanner;

impl BluetoothScanner {
    pub fn new() -> Self {
        Self
    }

    pub fn scan_devices(&self, only_connected: bool) -> Vec<BluetoothDevice> {
        let mut devices = Vec::new();
        unsafe {
            let hdevinfo = SetupDiGetClassDevsW(
                std::ptr::null(),
                std::ptr::null(),
                HWND::default(),
                DIGCF_PRESENT | DIGCF_ALLCLASSES,
            );
            if hdevinfo.is_invalid() {
                return devices;
            }

            let mut devinfo_data = SP_DEVINFO_DATA {
                cb_size: std::mem::size_of::<SP_DEVINFO_DATA>() as u32,
                class_guid: GUID::zeroed(),
                dev_inst: 0,
                reserved: 0,
            };

            let mut connected_macs = HashSet::new();
            struct RawEntry {
                name: String,
                inst_id: String,
                bat: i32,
                is_charging: bool,
                is_conn: Option<bool>,
                mac: Option<String>,
            }
            let mut raw_entries = Vec::new();

            let mut index = 0u32;
            while SetupDiEnumDeviceInfo(hdevinfo, index, &mut devinfo_data).as_bool() {
                let devinst = devinfo_data.dev_inst;
                let inst_id = get_devnode_property_string(devinst, &DEVPKEY_DEVICE_INSTANCE_ID)
                    .unwrap_or_default();
                let is_conn = get_devnode_property_bool(devinst, &DEVPKEY_DEVICE_IS_CONNECTED);
                let name = get_devnode_property_string(devinst, &DEVPKEY_DEVICE_FRIENDLY_NAME)
                    .or_else(|| get_devnode_property_string(devinst, &DEVPKEY_NAME))
                    .unwrap_or_default();

                let mac = extract_device_mac(&inst_id);
                if let Some(ref m) = mac {
                    if is_conn == Some(true) {
                        connected_macs.insert(m.clone());
                    }
                }

                if let Some(bat) = get_devnode_property_u8(devinst, &DEVPKEY_DEVICE_BATTERY_PERCENTAGE) {
                    if bat <= 100 {
                        let is_charging = get_devnode_property_bool(devinst, &DEVPKEY_DEVICE_IS_CHARGING)
                            .unwrap_or(false);
                        raw_entries.push(RawEntry {
                            name,
                            inst_id,
                            bat: bat as i32,
                            is_charging,
                            is_conn,
                            mac,
                        });
                    }
                }

                index += 1;
            }

            let _ = SetupDiDestroyDeviceInfoList(hdevinfo);

            let mut seen_names = HashSet::new();
            for entry in raw_entries {
                let is_active = (entry.is_conn == Some(true))
                    || entry.mac.as_ref().map(|m| connected_macs.contains(m)).unwrap_or(false);

                if only_connected && !is_active {
                    continue;
                }

                let clean_name = clean_device_name(&entry.name);
                if clean_name.len() > 20
                    && clean_name.contains('/')
                    && !["key", "mouse", "buds", "mic"].iter().any(|k| clean_name.to_lowercase().contains(k))
                {
                    continue;
                }

                if seen_names.contains(&clean_name) {
                    continue;
                }
                seen_names.insert(clean_name.clone());

                let icon = guess_device_icon(&clean_name, &entry.inst_id).to_string();
                devices.push(BluetoothDevice {
                    name: clean_name,
                    battery: entry.bat,
                    is_connected: true,
                    is_charging: entry.is_charging,
                    icon,
                });
            }
        }

        devices.sort_by_key(|d| d.battery);
        devices
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scan_bluetooth() {
        let scanner = BluetoothScanner::new();
        let devs = scanner.scan_devices(true);
        println!("Scanned {} connected Bluetooth devices:", devs.len());
        for d in &devs {
            println!("  {} {} ({}%)", d.icon, d.name, d.battery);
        }
    }
}
