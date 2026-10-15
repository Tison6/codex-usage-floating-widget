use chrono::{Local, TimeZone};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct WindowInfo {
    pub name: String,
    pub used_percent: i32,
    pub remaining_percent: i32,
    pub window_seconds: i64,
    pub reset_after_seconds: i64,
    pub reset_countdown: String,
    pub reset_at_str: String,
    pub bar_color: String,
    pub reset_at: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CodexUsageData {
    pub success: bool,
    pub error: Option<String>,
    pub plan_type: String,
    pub primary_window: Option<WindowInfo>,
    pub five_hour_window: Option<WindowInfo>,
    pub weekly_window: Option<WindowInfo>,
    pub reset_credits: i32,
    pub updated_at: String,
}

pub fn format_duration_compact(seconds: i64) -> String {
    if seconds <= 0 {
        return "即将重置".to_string();
    }
    let days = seconds / 86400;
    let hours = (seconds % 86400) / 3600;
    let minutes = (seconds % 3600) / 60;

    let mut parts = Vec::new();
    if days > 0 {
        parts.push(format!("{}d", days));
    }
    if hours > 0 {
        parts.push(format!("{}h", hours));
    }
    if minutes > 0 && days == 0 {
        parts.push(format!("{}m", minutes));
    }
    if parts.is_empty() {
        if minutes > 0 {
            parts.push(format!("{}m", minutes));
        } else {
            parts.push("<1m".to_string());
        }
    }
    parts.concat()
}

pub fn format_window_name_compact(window_seconds: i64) -> String {
    if window_seconds <= 18000 {
        "5H".to_string()
    } else if window_seconds <= 86400 {
        "24H".to_string()
    } else if window_seconds <= 604800 {
        "周限额".to_string()
    } else {
        format!("{}d", window_seconds / 86400)
    }
}

pub struct CodexUsageClient {
    auth_path: PathBuf,
    client: reqwest::Client,
    access_token: Option<String>,
    account_id: Option<String>,
    cached_data: Option<CodexUsageData>,
}

impl CodexUsageClient {
    pub fn new(auth_path_str: &str) -> Self {
        let path = if auth_path_str.starts_with('~') {
            if let Some(home) = dirs::home_dir() {
                home.join(&auth_path_str[2..])
            } else {
                PathBuf::from(auth_path_str)
            }
        } else {
            PathBuf::from(auth_path_str)
        };

        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(12))
            .build()
            .unwrap_or_default();

        Self {
            auth_path: path,
            client,
            access_token: None,
            account_id: None,
            cached_data: None,
        }
    }

    pub fn reload_auth(&mut self) -> bool {
        if self.auth_path.exists() {
            if let Ok(content) = fs::read_to_string(&self.auth_path) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(tokens) = val.get("tokens") {
                        if let Some(tok) = tokens.get("access_token").and_then(|v| v.as_str()) {
                            self.access_token = Some(tok.to_string());
                            self.account_id = tokens
                                .get("account_id")
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string());
                            return true;
                        }
                    }
                }
            }
        }
        false
    }

    pub async fn fetch_usage(&mut self) -> CodexUsageData {
        if !self.reload_auth() && self.access_token.is_none() {
            return CodexUsageData {
                success: false,
                error: Some("未找到认证凭证 (auth.json)".to_string()),
                plan_type: "未认证".to_string(),
                ..Default::default()
            };
        }

        let token = match &self.access_token {
            Some(t) => t.clone(),
            None => return CodexUsageData::default(),
        };

        let mut req = self
            .client
            .get("https://chatgpt.com/backend-api/wham/usage")
            .header("Authorization", format!("Bearer {}", token))
            .header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            .header("Accept", "application/json");

        if let Some(ref acct) = self.account_id {
            req = req.header("ChatGPT-Account-Id", acct);
        }

        match req.send().await {
            Ok(resp) => {
                let status = resp.status();
                if status.is_success() {
                    if let Ok(val) = resp.json::<serde_json::Value>().await {
                        let parsed = self.parse_response(&val);
                        self.cached_data = Some(parsed.clone());
                        return parsed;
                    }
                }
                CodexUsageData {
                    success: false,
                    error: Some(format!("HTTP 错误: {}", status)),
                    plan_type: "错误".to_string(),
                    ..Default::default()
                }
            }
            Err(e) => {
                if let Some(ref cached) = self.cached_data {
                    let mut ret = cached.clone();
                    ret.error = Some(format!("请求超时/异常: {}", e));
                    return ret;
                }
                CodexUsageData {
                    success: false,
                    error: Some(format!("网络请求失败: {}", e)),
                    plan_type: "超时".to_string(),
                    ..Default::default()
                }
            }
        }
    }

    fn parse_window(&self, val: &serde_json::Value) -> Option<WindowInfo> {
        let used_pct = val.get("used_percent")?.as_i64()? as i32;
        let remain_pct = (100 - used_pct).max(0);
        let win_secs = val.get("limit_window_seconds")?.as_i64()?;
        let reset_after = val.get("reset_after_seconds")?.as_i64()?;
        let reset_at = val.get("reset_at").and_then(|v| v.as_i64());

        let reset_at_str = if let Some(ts) = reset_at {
            Local
                .timestamp_opt(ts, 0)
                .single()
                .map(|dt| dt.format("%m-%d %H:%M").to_string())
                .unwrap_or_default()
        } else {
            String::new()
        };

        let bar_color = if remain_pct > 30 {
            "#3B82F6".to_string()
        } else if remain_pct > 10 {
            "#F59E0B".to_string()
        } else {
            "#EF4444".to_string()
        };

        Some(WindowInfo {
            name: format_window_name_compact(win_secs),
            used_percent: used_pct,
            remaining_percent: remain_pct,
            window_seconds: win_secs,
            reset_after_seconds: reset_after,
            reset_countdown: format_duration_compact(reset_after),
            reset_at_str,
            bar_color,
            reset_at,
        })
    }

    fn parse_response(&self, raw: &serde_json::Value) -> CodexUsageData {
        let plan_type = raw
            .get("plan_type")
            .and_then(|v| v.as_str())
            .unwrap_or("PLUS")
            .to_uppercase();

        let rate_limit = raw.get("rate_limit").unwrap_or(&serde_json::Value::Null);

        let pw = rate_limit
            .get("primary_window")
            .and_then(|v| self.parse_window(v));
        let sw = rate_limit
            .get("secondary_window")
            .and_then(|v| self.parse_window(v));

        let mut five_hour = None;
        let mut weekly = None;

        let mut windows = Vec::new();
        if let Some(w) = pw.clone() {
            windows.push(w);
        }
        if let Some(w) = sw {
            windows.push(w);
        }

        if let Some(add_arr) = raw
            .get("additional_rate_limits")
            .and_then(|v| v.as_array())
        {
            for a in add_arr {
                if let Some(w) = self.parse_window(a) {
                    windows.push(w);
                }
            }
        }

        for w in windows {
            if w.window_seconds <= 18000 && five_hour.is_none() {
                five_hour = Some(w.clone());
            } else if w.window_seconds > 86400 && weekly.is_none() {
                weekly = Some(w.clone());
            } else if weekly.is_none() {
                weekly = Some(w);
            }
        }

        if weekly.is_none() {
            weekly = pw.clone();
        }

        let reset_credits = raw
            .get("rate_limit_reset_credits")
            .and_then(|v| v.get("available_count"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0) as i32;

        let now = Local::now().format("%H:%M").to_string();

        CodexUsageData {
            success: true,
            error: None,
            plan_type,
            primary_window: pw,
            five_hour_window: five_hour,
            weekly_window: weekly,
            reset_credits,
            updated_at: now,
        }
    }
}

pub struct CodexActivityTracker {
    codex_home: PathBuf,
}

impl CodexActivityTracker {
    pub fn new() -> Self {
        let home = dirs::home_dir()
            .map(|h| h.join(".codex"))
            .unwrap_or_else(|| PathBuf::from(".codex"));
        Self { codex_home: home }
    }

    pub fn check_is_running(&self) -> (bool, String) {
        let db_path = self.codex_home.join("state_5.sqlite");
        if !db_path.exists() {
            return (false, "no_db".to_string());
        }

        if let Ok(conn) = Connection::open_with_flags(
            &db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
                | rusqlite::OpenFlags::SQLITE_OPEN_URI,
        ) {
            let mut stmt = match conn.prepare(
                "SELECT rollout_path FROM threads WHERE source NOT LIKE '%subagent%' ORDER BY updated_at DESC LIMIT 3"
            ) {
                Ok(s) => s,
                Err(_) => return (false, "err_stmt".to_string()),
            };

            let paths: Vec<String> = stmt
                .query_map([], |row| row.get(0))
                .map(|rows| rows.filter_map(Result::ok).collect())
                .unwrap_or_default();

            for rpath in paths {
                let clean = rpath
                    .replace(r"\\?\ ", "")
                    .replace(r"\\?\/", "")
                    .replace(r"\\?\\", "");
                let p = Path::new(&clean);
                if p.exists() {
                    let (running, reason) = self.check_file_running(p);
                    if running {
                        return (true, reason);
                    }
                }
            }
        }

        (false, "idle".to_string())
    }

    fn check_file_running(&self, path: &Path) -> (bool, String) {
        let metadata = match fs::metadata(path) {
            Ok(m) => m,
            Err(_) => return (false, "err_meta".to_string()),
        };

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();
        let mtime = metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let age = now - mtime;
        if age > 90.0 {
            return (false, format!("timeout_{:.0}s", age));
        }

        // Read last 64KB to check lifecycle events
        if let Ok(mut f) = File::open(path) {
            let len = metadata.len();
            let read_sz = len.min(65536);
            if f.seek(SeekFrom::End(-(read_sz as i64))).is_ok() {
                let mut buf = vec![0u8; read_sz as usize];
                if f.read_exact(&mut buf).is_ok() {
                    let text = String::from_utf8_lossy(&buf);
                    // Search backward line by line
                    for line in text.lines().rev() {
                        if line.contains("task_complete")
                            || line.contains("task_failed")
                            || line.contains("turn_aborted")
                        {
                            return (false, "completed".to_string());
                        }
                        if line.contains("task_started") {
                            return (true, "running".to_string());
                        }
                    }
                }
            }
        }

        (false, "idle".to_string())
    }
}
