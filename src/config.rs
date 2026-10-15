use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    pub id: String,
    pub name: String,
    pub host: String,
    pub port: u16,
    pub user: String,
    #[serde(default)]
    pub password: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    #[serde(default = "default_window_pos")]
    pub window_pos: [i32; 2],
    #[serde(default = "default_true")]
    pub is_mini_mode: bool,
    #[serde(default = "default_true")]
    pub always_on_top: bool,
    #[serde(default)]
    pub lock_position: bool,
    #[serde(default = "default_true")]
    pub auto_snap: bool,
    #[serde(default = "default_opacity")]
    pub opacity: f32,
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default = "default_interval")]
    pub bt_interval_sec: u64,
    #[serde(default = "default_interval")]
    pub codex_interval_sec: u64,
    #[serde(default = "default_interval")]
    pub relay_interval_sec: u64,
    #[serde(default = "default_auth_file")]
    pub auth_file_path: String,
    #[serde(default)]
    pub autostart: bool,
    #[serde(default)]
    pub aihub_email: String,
    #[serde(default)]
    pub aihub_password: String,
    #[serde(default = "default_scale")]
    pub scale: f32,
    #[serde(default = "default_true")]
    pub only_connected: bool,
    #[serde(default)]
    pub mini_quota_mode: i32,
    #[serde(default)]
    pub square_selected_groups: Vec<String>,
    #[serde(default)]
    pub square_selected_models: Vec<String>,
    #[serde(default)]
    pub square_group_models: HashMap<String, String>,
    #[serde(default)]
    pub aihub_selected_providers: Vec<String>,
    #[serde(default)]
    pub aihub_excluded_providers: Vec<String>,
    #[serde(default = "default_true")]
    pub aihub_auto_mode: bool,
    #[serde(default)]
    pub servers: Vec<ServerConfig>,
}

fn default_window_pos() -> [i32; 2] {
    [778, 28]
}
fn default_true() -> bool {
    true
}
fn default_opacity() -> f32 {
    1.0
}
fn default_theme() -> String {
    "dark".to_string()
}
fn default_interval() -> u64 {
    60
}
fn default_auth_file() -> String {
    "~/.codex/auth.json".to_string()
}
fn default_scale() -> f32 {
    1.4
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            window_pos: default_window_pos(),
            is_mini_mode: true,
            always_on_top: true,
            lock_position: false,
            auto_snap: true,
            opacity: default_opacity(),
            theme: default_theme(),
            bt_interval_sec: 60,
            codex_interval_sec: 60,
            relay_interval_sec: 60,
            auth_file_path: default_auth_file(),
            autostart: false,
            aihub_email: String::new(),
            aihub_password: String::new(),
            scale: default_scale(),
            only_connected: true,
            mini_quota_mode: 0,
            square_selected_groups: vec![],
            square_selected_models: vec![],
            square_group_models: HashMap::new(),
            aihub_selected_providers: vec![],
            aihub_excluded_providers: vec![],
            aihub_auto_mode: true,
            servers: vec![],
        }
    }
}

pub struct ConfigManager {
    file_path: PathBuf,
    config: Arc<Mutex<AppConfig>>,
}

impl ConfigManager {
    pub fn new<P: AsRef<Path>>(path: P) -> Self {
        let p = path.as_ref().to_path_buf();
        let loaded = Self::load_from_path(&p);
        Self {
            file_path: p,
            config: Arc::new(Mutex::new(loaded)),
        }
    }

    fn load_from_path(path: &Path) -> AppConfig {
        if path.exists() {
            if let Ok(content) = fs::read_to_string(path) {
                if let Ok(cfg) = serde_json::from_str::<AppConfig>(&content) {
                    return cfg;
                }
            }
        }
        AppConfig::default()
    }

    pub fn get(&self) -> AppConfig {
        self.config.lock().unwrap().clone()
    }

    pub fn update<F>(&self, f: F)
    where
        F: FnOnce(&mut AppConfig),
    {
        let mut cfg = self.config.lock().unwrap();
        f(&mut cfg);
        if let Ok(serialized) = serde_json::to_string_pretty(&*cfg) {
            let _ = fs::write(&self.file_path, serialized);
        }
    }
}
