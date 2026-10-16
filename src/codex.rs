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
        let trimmed = auth_path_str.trim();
        let path = if trimmed.starts_with('~') {
            if let Some(home) = dirs::home_dir() {
                let sub = trimmed[1..].trim_start_matches(['/', '\\']);
                home.join(sub)
            } else {
                PathBuf::from(trimmed)
            }
        } else {
            PathBuf::from(trimmed)
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
        // 1. Try auth.json
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

        // 2. Fallback to CC Switch database (~/.cc-switch/cc-switch.db)
        if let Some(home) = dirs::home_dir() {
            let db_path = home.join(".cc-switch").join("cc-switch.db");
            if db_path.exists() {
                if let Ok(conn) = Connection::open_with_flags(
                    &db_path,
                    rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI,
                ) {
                    if let Ok(mut stmt) = conn.prepare(
                        "SELECT settings_config FROM providers WHERE app_type='codex' AND (name LIKE '%Official%' OR name LIKE '%OpenAI%')"
                    ) {
                        let rows: Vec<String> = stmt
                            .query_map([], |row| row.get(0))
                            .map(|r| r.filter_map(Result::ok).collect())
                            .unwrap_or_default();
                        for settings_raw in rows {
                            if let Ok(settings) = serde_json::from_str::<serde_json::Value>(&settings_raw) {
                                if let Some(tokens) = settings.get("auth").and_then(|a| a.get("tokens")) {
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
                if status.as_u16() == 401 {
                    return CodexUsageData {
                        success: false,
                        error: Some("登录凭证失效 (401)".to_string()),
                        plan_type: "未登录".to_string(),
                        ..Default::default()
                    };
                }
                if status.as_u16() == 429 {
                    return CodexUsageData {
                        success: false,
                        error: Some("请求频繁 (429)".to_string()),
                        plan_type: "限频".to_string(),
                        ..Default::default()
                    };
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
        // 1. Check state_5.sqlite interactive threads first
        let db_path = self.codex_home.join("state_5.sqlite");
        if db_path.exists() {
            if let Ok(conn) = Connection::open_with_flags(
                &db_path,
                rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
                    | rusqlite::OpenFlags::SQLITE_OPEN_URI,
            ) {
                if let Ok(mut stmt) = conn.prepare(
                    "SELECT rollout_path FROM threads WHERE source NOT LIKE '%subagent%' ORDER BY updated_at DESC LIMIT 3"
                ) {
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
            }
        }

        // 2. Check today's sessions directory (handles new sessions not yet committed to DB or CLI runs)
        for p in self.find_recent_sessions() {
            let (running, reason) = self.check_file_running(&p);
            if running {
                return (true, reason);
            }
        }

        (false, "idle".to_string())
    }

    fn find_recent_sessions(&self) -> Vec<PathBuf> {
        let sessions_dir = self.codex_home.join("sessions");
        if !sessions_dir.exists() {
            return Vec::new();
        }
        let mut files: Vec<(PathBuf, f64)> = Vec::new();

        let mut dirs_to_visit = vec![sessions_dir];
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();

        while let Some(current) = dirs_to_visit.pop() {
            if let Ok(entries) = fs::read_dir(current) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() {
                        dirs_to_visit.push(path);
                    } else if path.extension().and_then(|e| e.to_str()) == Some("jsonl") {
                        if let Ok(meta) = entry.metadata() {
                            let mtime = meta
                                .modified()
                                .ok()
                                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                                .map(|d| d.as_secs_f64())
                                .unwrap_or(0.0);
                            if (now - mtime) < 180.0 {
                                files.push((path, mtime));
                            }
                        }
                    }
                }
            }
        }
        files.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        files.into_iter().take(3).map(|(p, _)| p).collect()
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

        // Read up to 256KB from tail
        if let Ok(mut f) = File::open(path) {
            let len = metadata.len();
            let read_sz = len.min(262144);
            if f.seek(SeekFrom::End(-(read_sz as i64))).is_ok() {
                let mut buf = vec![0u8; read_sz as usize];
                if f.read_exact(&mut buf).is_ok() {
                    let text = String::from_utf8_lossy(&buf);
                    let mut last_active_event: Option<String> = None;
                    for line in text.lines().rev() {
                        let l = line.trim();
                        if l.is_empty() {
                            continue;
                        }
                        if let Ok(val) = serde_json::from_str::<serde_json::Value>(l) {
                            let p = val.get("payload");
                            let pt = p.and_then(|p| p.get("type")).and_then(|t| t.as_str()).unwrap_or("");
                            if matches!(pt, "task_complete" | "task_failed" | "turn_aborted" | "turn_complete") {
                                return (false, format!("completed_{}", pt));
                            }
                            if pt == "task_started" {
                                return (true, "task_started_active".to_string());
                            }
                            if last_active_event.is_none() && matches!(pt, "custom_tool_call" | "reasoning" | "custom_tool_call_output" | "item_started") {
                                last_active_event = Some(pt.to_string());
                            }
                        }
                    }
                    if let Some(event) = last_active_event {
                        if age < 8.0 {
                            return (true, format!("active_{}", event));
                        }
                    }
                }
            }
        }

        (false, "idle".to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuotaSnapshot {
    pub timestamp: i64,
    pub used_percent: i32,
    pub remaining_percent: i32,
    pub reset_at: i64,
    pub plan_type: String,
}

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct CycleAnalysis {
    pub has_data: bool,
    pub current_remain: i32,
    pub ideal_remain: f64,
    pub pace_status: String,
    pub exhaustion_text: String,
    pub curve_points: Vec<(f64, f64)>, // (t_norm, r_norm)
    pub cycle_progress: f64,
}

pub struct QuotaTracker {
    history_file: PathBuf,
    history: Vec<QuotaSnapshot>,
}

impl QuotaTracker {
    pub fn new(data_dir_str: &str) -> Self {
        let dir = PathBuf::from(data_dir_str);
        let _ = fs::create_dir_all(&dir);
        let history_file = dir.join("quota_history.json");
        let history = Self::load_history(&history_file);
        Self {
            history_file,
            history,
        }
    }

    fn load_history(path: &Path) -> Vec<QuotaSnapshot> {
        if path.exists() {
            if let Ok(content) = fs::read_to_string(path) {
                if let Ok(items) = serde_json::from_str::<Vec<QuotaSnapshot>>(&content) {
                    return items;
                }
            }
        }
        Vec::new()
    }

    pub fn save_history(&self) {
        if let Ok(json) = serde_json::to_string_pretty(&self.history) {
            let _ = fs::write(&self.history_file, json);
        }
    }

    pub fn record_snapshot(&mut self, codex_data: &CodexUsageData) {
        if !codex_data.success {
            return;
        }
        let w = match codex_data.weekly_window.as_ref().or(codex_data.primary_window.as_ref()) {
            Some(w) => w,
            None => return,
        };

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);
        let used = w.used_percent;
        let remain = w.remaining_percent;
        let reset_at = w.reset_at.unwrap_or(now + w.reset_after_seconds);

        if let Some(last) = self.history.last() {
            if last.reset_at == reset_at && last.remaining_percent == remain && (now - last.timestamp < 180) {
                return;
            }
        }

        self.history.push(QuotaSnapshot {
            timestamp: now,
            used_percent: used,
            remaining_percent: remain,
            reset_at,
            plan_type: codex_data.plan_type.clone(),
        });

        let cutoff = now - (30 * 86400);
        self.history.retain(|h| h.timestamp >= cutoff);
        self.save_history();
    }

    pub fn get_analysis_for_current_cycle(&self, window: Option<&WindowInfo>) -> CycleAnalysis {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);

        let (reset_at, current_remain, window_seconds) = if let Some(w) = window {
            (
                w.reset_at.unwrap_or(now + w.reset_after_seconds),
                w.remaining_percent,
                if w.window_seconds > 0 { w.window_seconds } else { 604800 },
            )
        } else if let Some(last) = self.history.last() {
            (last.reset_at, last.remaining_percent, 604800)
        } else {
            return CycleAnalysis {
                has_data: false,
                current_remain: 100,
                ideal_remain: 100.0,
                pace_status: "未知".to_string(),
                exhaustion_text: "暂无数据".to_string(),
                curve_points: Vec::new(),
                cycle_progress: 0.0,
            };
        };

        let cycle_start = reset_at - window_seconds;
        let cycle_end = reset_at;

        let cycle_points: Vec<&QuotaSnapshot> = self
            .history
            .iter()
            .filter(|p| p.reset_at == reset_at && p.timestamp >= cycle_start && p.timestamp <= cycle_end)
            .collect();

        let mut normalized_points: Vec<(f64, f64)> = Vec::new();
        normalized_points.push((0.0, 100.0));

        for p in cycle_points {
            let t_norm = ((p.timestamp - cycle_start) as f64 / window_seconds as f64).clamp(0.0, 1.0);
            let r_val = p.remaining_percent as f64;
            normalized_points.push((t_norm, r_val));
        }

        let now_norm = ((now - cycle_start) as f64 / window_seconds as f64).clamp(0.0, 1.0);
        if normalized_points.is_empty() || normalized_points.last().map(|p| p.0 < now_norm).unwrap_or(true) {
            normalized_points.push((now_norm, current_remain as f64));
        }

        normalized_points.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

        let ideal_remain = (100.0 * (1.0 - now_norm)).max(0.0);
        let elapsed_secs = (now - cycle_start).max(1800) as f64;
        let used_total = 100.0 - current_remain as f64;
        let burn_rate_per_hour = (used_total / elapsed_secs) * 3600.0;

        let (exhaustion_text, pace_status) = if burn_rate_per_hour > 0.01 {
            let hours_to_zero = (current_remain as f64) / burn_rate_per_hour;
            let secs_to_zero = (hours_to_zero * 3600.0) as i64;
            let exhaust_ts = now + secs_to_zero;

            let exhaust_date_str = Local
                .timestamp_opt(exhaust_ts, 0)
                .single()
                .map(|dt| dt.format("%m-%d %H:%M").to_string())
                .unwrap_or_default();
            let dur_str = format_duration_compact(secs_to_zero);

            if exhaust_ts < reset_at {
                (format!("预计耗尽: {} ({})", dur_str, exhaust_date_str), "消耗偏快".to_string())
            } else {
                let end_surplus = (100.0 - (burn_rate_per_hour * (window_seconds as f64 / 3600.0))).max(0.0) as i32;
                (format!("速率稳定: 周期末余 ~{}%", end_surplus), "良好".to_string())
            }
        } else {
            ("消耗极低: 可用至重置".to_string(), "充足".to_string())
        };

        CycleAnalysis {
            has_data: true,
            current_remain,
            ideal_remain,
            pace_status,
            exhaustion_text,
            curve_points: normalized_points,
            cycle_progress: now_norm,
        }
    }

    pub fn generate_sparkline_svg(&self, analysis: &CycleAnalysis, width: f64, height: f64) -> String {
        let pad_l = 8.0;
        let pad_r = 8.0;
        let pad_t = 6.0;
        let pad_b = 14.0;
        let chart_w = (width - pad_l - pad_r).max(10.0);
        let chart_h = (height - pad_t - pad_b).max(10.0);

        let mut svg = format!(
            r##"<svg xmlns="http://www.w3.org/2000/svg" width="{:.0}" height="{:.0}" viewBox="0 0 {:.0} {:.0}">
  <defs>
    <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3B82F6" stop-opacity="0.45" />
      <stop offset="100%" stop-color="#3B82F6" stop-opacity="0.04" />
    </linearGradient>
  </defs>
  <!-- Background Box -->
  <rect x="0" y="0" width="{:.0}" height="{:.0}" rx="6" ry="6" fill="#0D1117" fill-opacity="0.8" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
  <!-- Coordinate Grid Frame -->
  <rect x="{:.1}" y="{:.1}" width="{:.1}" height="{:.1}" fill="rgba(0,0,0,0.18)" stroke="rgba(255,255,255,0.1)" stroke-width="1" />
"##,
            width, height, width, height, width, height, pad_l, pad_t, chart_w, chart_h
        );

        // Y-axis horizontal grid lines (every 10%)
        for i in 1..10 {
            let y_i = pad_t + (chart_h * (i as f64 / 10.0));
            let (dash, op) = if i == 5 { ("3,3", "0.12") } else { ("1,3", "0.06") };
            svg.push_str(&format!(
                r##"  <line x1="{:.1}" y1="{:.1}" x2="{:.1}" y2="{:.1}" stroke="rgba(255,255,255,{})" stroke-dasharray="{}" stroke-width="1" />
"##,
                pad_l, y_i, pad_l + chart_w, y_i, op, dash
            ));
        }

        // X-axis vertical grid lines (day 1..6)
        for d in 1..7 {
            let x_d = pad_l + (chart_w * (d as f64 / 7.0));
            svg.push_str(&format!(
                r##"  <line x1="{:.1}" y1="{:.1}" x2="{:.1}" y2="{:.1}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="1,3" stroke-width="1" />
"##,
                x_d, pad_t, x_d, pad_t + chart_h
            ));
        }

        // Ideal Baseline ((0, 100%) -> (7d, 0%))
        svg.push_str(&format!(
            r##"  <line x1="{:.1}" y1="{:.1}" x2="{:.1}" y2="{:.1}" stroke="#9CA3AF" stroke-opacity="0.55" stroke-dasharray="3,3" stroke-width="1.2" />
"##,
            pad_l, pad_t, pad_l + chart_w, pad_t + chart_h
        ));

        // Actual Usage Curve
        if analysis.curve_points.len() >= 2 {
            let mut pixel_points = Vec::new();
            for (t_norm, r_norm) in &analysis.curve_points {
                let px = pad_l + (t_norm * chart_w);
                let py = pad_t + ((100.0 - r_norm) / 100.0 * chart_h);
                pixel_points.push((px, py));
            }

            // Fill polygon under curve
            let mut poly = format!("{:.1},{:.1} ", pixel_points[0].0, pad_t + chart_h);
            for pt in &pixel_points {
                poly.push_str(&format!("{:.1},{:.1} ", pt.0, pt.1));
            }
            poly.push_str(&format!("{:.1},{:.1}", pixel_points.last().unwrap().0, pad_t + chart_h));

            svg.push_str(&format!(
                r##"  <polygon points="{}" fill="url(#curveGrad)" />
"##,
                poly
            ));

            // Curve stroke line
            let mut path_d = format!("M {:.1} {:.1}", pixel_points[0].0, pixel_points[0].1);
            for pt in &pixel_points[1..] {
                path_d.push_str(&format!(" L {:.1} {:.1}", pt.0, pt.1));
            }

            svg.push_str(&format!(
                r##"  <path d="{}" fill="none" stroke="#60A5FA" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
"##,
                path_d
            ));

            // Glowing dot at current position
            if let Some(last_pt) = pixel_points.last() {
                svg.push_str(&format!(
                    r##"  <circle cx="{:.1}" cy="{:.1}" r="5" fill="#3B82F6" fill-opacity="0.4" />
  <circle cx="{:.1}" cy="{:.1}" r="2" fill="#FFFFFF" />
"##,
                    last_pt.0, last_pt.1, last_pt.0, last_pt.1
                ));
            }
        }

        // Day Ticks text
        let y_txt = height - 2.5;
        svg.push_str(&format!(
            r##"  <text x="{:.1}" y="{:.1}" font-family="Segoe UI, sans-serif" font-size="7.5" fill="#9CA3AF" fill-opacity="0.7">1d</text>
  <text x="{:.1}" y="{:.1}" font-family="Segoe UI, sans-serif" font-size="7.5" fill="#9CA3AF" fill-opacity="0.7">3d</text>
  <text x="{:.1}" y="{:.1}" font-family="Segoe UI, sans-serif" font-size="7.5" fill="#9CA3AF" fill-opacity="0.7">5d</text>
  <text x="{:.1}" y="{:.1}" font-family="Segoe UI, sans-serif" font-size="7.5" fill="#9CA3AF" fill-opacity="0.7">7d</text>
</svg>"##,
            pad_l - 1.0, y_txt,
            pad_l + (chart_w * 0.28) - 4.0, y_txt,
            pad_l + (chart_w * 0.57) - 4.0, y_txt,
            pad_l + chart_w - 9.0, y_txt
        ));

        svg
    }
}
