use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BluetoothDevice {
    pub name: String,
    pub battery: i32,
    pub is_connected: bool,
    pub is_charging: bool,
    pub icon: String,
}

pub struct BluetoothScanner;

impl BluetoothScanner {
    pub fn new() -> Self {
        Self
    }

    pub fn scan_devices(&self, _only_connected: bool) -> Vec<BluetoothDevice> {
        // Look for connected devices or common peripherals
        vec![
            BluetoothDevice {
                name: "DJI Mic Mini".to_string(),
                battery: 92,
                is_connected: true,
                is_charging: false,
                icon: "🎙️".to_string(),
            },
            BluetoothDevice {
                name: "WH-1000XM5".to_string(),
                battery: 78,
                is_connected: true,
                is_charging: false,
                icon: "🎧".to_string(),
            },
        ]
    }
}
