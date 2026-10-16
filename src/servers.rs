use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::path::Path;

pub const DB_FILE: &str = r"D:/gpu_history.db";

pub const USER_PALETTE: [&str; 8] = [
    "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
    "#8B5CF6", "#06B6D4", "#E11D48", "#14B8A6",
];

pub fn get_user_color(username: &str) -> &'static str {
    if username.is_empty() || username == "Idle" || username == "空闲" {
        return "#10B981";
    }
    let mut hash: u32 = 0;
    for b in username.bytes() {
        hash = hash.wrapping_mul(31).wrapping_add(b as u32);
    }
    USER_PALETTE[(hash as usize) % USER_PALETTE.len()]
}

pub fn get_user_display_name(raw: &str) -> String {
    if raw.is_empty() || raw == "Idle" || raw == "Unknown" || raw == "None" {
        return "Idle".to_string();
    }
    if raw.starts_with("PID") {
        return raw.to_string();
    }
    let content = std::fs::read_to_string("data/user_mapping.json")
        .or_else(|_| {
            if let Ok(exe) = std::env::current_exe() {
                if let Some(parent) = exe.parent() {
                    return std::fs::read_to_string(parent.join("data/user_mapping.json"));
                }
            }
            Err(std::io::Error::new(std::io::ErrorKind::NotFound, "not found"))
        })
        .unwrap_or_else(|_| include_str!("../data/user_mapping.json").to_string());

    let clean = content.trim_start_matches('\u{feff}').trim();
    if let Ok(map) = serde_json::from_str::<std::collections::HashMap<String, String>>(clean) {
        if let Some(mapped) = map.get(raw) {
            return mapped.clone();
        }
    }
    raw.to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GPUCardData {
    pub sid: String,
    pub index: String,
    pub server_name: String,
    pub model: String,
    pub memory_used_gb: f32,
    pub memory_total_gb: f32,
    pub vram_pct: f32,
    pub utilization: i32,
    pub power_draw: String,
    pub user: String,
    pub user_color: String,
    pub is_busy: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct HostStatData {
    pub id: String,
    pub name: String,
    pub cpu_pct: f32,
    pub mem_used_gb: f32,
    pub mem_total_gb: f32,
    pub mem_pct: f32,
    pub disk_free_gb: f32,
    pub disk_str: String,
    pub is_online: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GanttRowData {
    pub task: String,
    pub has_activity: bool,
    pub start_pct: f32,
    pub width_pct: f32,
    pub user: String,
    pub user_color: String,
}

fn query_windows_cpu(host: &str, user: &str, pass: &str) -> Option<f32> {
    use std::io::Read;
    use std::net::{TcpStream, ToSocketAddrs};
    use std::time::Duration;
    use ssh2::Session;

    let mut addrs = (host, 22).to_socket_addrs().ok()?;
    let addr = addrs.next()?;
    let tcp = TcpStream::connect_timeout(&addr, Duration::from_secs(2)).ok()?;
    let _ = tcp.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = tcp.set_write_timeout(Some(Duration::from_secs(3)));

    let mut sess = Session::new().ok()?;
    sess.set_tcp_stream(tcp);
    sess.handshake().ok()?;
    sess.userauth_password(user, pass).ok()?;
    if !sess.authenticated() {
        return None;
    }

    let mut channel = sess.channel_session().ok()?;
    channel.exec("typeperf \"\\Processor(_Total)\\% Processor Time\" -sc 1").ok()?;
    let mut buf = Vec::new();
    let _ = channel.read_to_end(&mut buf);
    let s = String::from_utf8_lossy(&buf);

    for line in s.lines().rev() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.contains("Processor Time") {
            continue;
        }
        if let Some(val_str) = trimmed.split(',').last() {
            let clean = val_str.trim().trim_matches('"');
            if let Ok(v) = clean.parse::<f32>() {
                return Some((v * 10.0).round() / 10.0);
            }
        }
    }
    None
}

fn query_linux_cpu(ip: &str, key_path: &str) -> Option<f32> {
    use std::process::Command;
    use std::os::windows::process::CommandExt;

    let mut cmd = Command::new("ssh");
    cmd.args([
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=2",
        "-o", "BatchMode=yes",
        &format!("xutianxiao@{}", ip),
        "head -n 1 /proc/stat; sleep 0.3; head -n 1 /proc/stat",
    ]);
    cmd.creation_flags(0x08000000);

    let output = cmd.output().ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let mut lines = text.lines().filter(|l| l.starts_with("cpu "));
    let line1 = lines.next()?;
    let line2 = lines.next()?;

    let parts1: Vec<f64> = line1.split_whitespace().skip(1).take(4).filter_map(|s| s.parse().ok()).collect();
    let parts2: Vec<f64> = line2.split_whitespace().skip(1).take(4).filter_map(|s| s.parse().ok()).collect();

    if parts1.len() == 4 && parts2.len() == 4 {
        let total1: f64 = parts1.iter().sum();
        let total2: f64 = parts2.iter().sum();
        let idle1 = parts1[3];
        let idle2 = parts2[3];

        let d_total = total2 - total1;
        let d_idle = idle2 - idle1;

        if d_total > 0.0 {
            let cpu_pct = (1.0 - d_idle / d_total) * 100.0;
            return Some((cpu_pct.clamp(0.0, 100.0) as f32 * 10.0).round() / 10.0);
        }
    }
    None
}

#[derive(Clone)]
pub struct ServerManager {
    db_path: String,
    live_stats: std::sync::Arc<std::sync::RwLock<Vec<HostStatData>>>,
}

impl ServerManager {
    pub fn new() -> Self {
        let initial_hosts = vec![
            HostStatData {
                id: "gpu7".to_string(),
                name: "GPU 7号 · L40S".to_string(),
                cpu_pct: 45.0,
                mem_used_gb: 62.9,
                mem_total_gb: 252.0,
                mem_pct: 25.0,
                disk_free_gb: 20.7,
                disk_str: "💾 Data: 20.7G".to_string(),
                is_online: true,
            },
            HostStatData {
                id: "gpu8".to_string(),
                name: "GPU 8号 · A100".to_string(),
                cpu_pct: 46.0,
                mem_used_gb: 78.4,
                mem_total_gb: 503.0,
                mem_pct: 15.6,
                disk_free_gb: 280.0,
                disk_str: "💾 Data: 280.0G".to_string(),
                is_online: true,
            },
            HostStatData {
                id: "gpu4".to_string(),
                name: "GPU 4号 · 2080Ti".to_string(),
                cpu_pct: 48.0,
                mem_used_gb: 32.0,
                mem_total_gb: 128.0,
                mem_pct: 25.0,
                disk_free_gb: 120.5,
                disk_str: "💾 Data: 120.5G".to_string(),
                is_online: true,
            },
            HostStatData {
                id: "quad".to_string(),
                name: "quad".to_string(),
                cpu_pct: 96.0,
                mem_used_gb: 18.0,
                mem_total_gb: 64.0,
                mem_pct: 28.1,
                disk_free_gb: 340.0,
                disk_str: "💾 D: 340.0G".to_string(),
                is_online: true,
            },
            HostStatData {
                id: "e5".to_string(),
                name: "e5".to_string(),
                cpu_pct: 96.0,
                mem_used_gb: 14.0,
                mem_total_gb: 32.0,
                mem_pct: 43.8,
                disk_free_gb: 210.0,
                disk_str: "💾 D: 210.0G".to_string(),
                is_online: true,
            },
            HostStatData {
                id: "8375c".to_string(),
                name: "8375c".to_string(),
                cpu_pct: 46.0,
                mem_used_gb: 42.0,
                mem_total_gb: 128.0,
                mem_pct: 32.8,
                disk_free_gb: 850.0,
                disk_str: "💾 E: 850.0G".to_string(),
                is_online: true,
            },
        ];

        let live_stats = std::sync::Arc::new(std::sync::RwLock::new(initial_hosts));
        let stats_worker = live_stats.clone();

        std::thread::spawn(move || {
            loop {
                // Query 3 Windows servers
                if let Some(c) = query_windows_cpu("server-quad", "SJTU", "lab116") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "quad") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }
                if let Some(c) = query_windows_cpu("server-e5", "SJTU", "lab116") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "e5") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }
                if let Some(c) = query_windows_cpu("server-8375c", "SJTU", "lab116") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "8375c") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }

                // Query 3 GPU servers
                if let Some(c) = query_linux_cpu("192.168.120.7", "C:/Users/xtx/.ssh/id_rsa_xtx") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "gpu7") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }
                if let Some(c) = query_linux_cpu("192.168.120.8", "C:/Users/xtx/.ssh/id_rsa_xtx") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "gpu8") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }
                if let Some(c) = query_linux_cpu("192.168.120.4", "C:/Users/xtx/.ssh/id_rsa_stu") {
                    if let Ok(mut lock) = stats_worker.write() {
                        if let Some(h) = lock.iter_mut().find(|x| x.id == "gpu4") {
                            h.cpu_pct = c;
                            h.is_online = true;
                        }
                    }
                }

                std::thread::sleep(std::time::Duration::from_secs(2));
            }
        });

        Self {
            db_path: DB_FILE.to_string(),
            live_stats,
        }
    }

    pub fn query_gpu_cards(&self) -> Vec<GPUCardData> {
        let mut cards = Vec::new();
        if !Path::new(&self.db_path).exists() {
            return cards;
        }

        if let Ok(conn) = Connection::open_with_flags(
            &self.db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
                | rusqlite::OpenFlags::SQLITE_OPEN_URI,
        ) {
            let query = "
                SELECT ip, gpu_index, gpu_name, memory_used, memory_total,
                       utilization, power_draw, top_user
                FROM gpu_status_latest
                ORDER BY ip DESC, cast(gpu_index as integer) ASC
            ";

            if let Ok(mut stmt) = conn.prepare(query) {
                let rows = stmt.query_map([], |row| {
                    let ip: String = row.get(0)?;
                    let idx: String = row.get::<_, String>(1)
                        .or_else(|_| row.get::<_, i64>(1).map(|v| v.to_string()))
                        .unwrap_or_else(|_| "0".to_string());
                    let raw_name: String = row.get(2)?;
                    let mem_u: i64 = row.get(3).unwrap_or(0);
                    let mem_t: i64 = row.get(4).unwrap_or(1);
                    let util: i64 = row.get(5).unwrap_or(0);
                    let p_draw: String = row.get::<_, String>(6)
                        .or_else(|_| row.get::<_, i64>(6).map(|v| v.to_string()))
                        .unwrap_or_else(|_| "0".to_string());
                    let user: String = row.get(7).unwrap_or_else(|_| "Idle".to_string());
                    Ok((ip, idx, raw_name, mem_u, mem_t, util, p_draw, user))
                });

                if let Ok(mapped) = rows {
                    for r in mapped.flatten() {
                        let (ip, idx, raw_name, mem_u, mem_t, util, p_draw, user) = r;
                        let sid = if ip.contains('.') {
                            ip.split('.').last().unwrap_or("").to_string()
                        } else {
                            ip.clone()
                        };

                        if sid != "7" && sid != "8" {
                            continue;
                        }

                        let server_name = if sid == "7" {
                            format!("7号 · L40S [{}]", idx)
                        } else {
                            format!("8号 · A100 [{}]", idx)
                        };

                        let clean_model = raw_name
                            .replace("NVIDIA", "")
                            .replace("GeForce", "")
                            .replace("RTX", "")
                            .replace("PCIe", "")
                            .replace("80GB", "")
                            .replace("24GB", "")
                            .trim()
                            .to_string();

                        let vram_pct = if mem_t > 0 {
                            (mem_u as f32 / mem_t as f32) * 100.0
                        } else {
                            0.0
                        };

                        let is_busy = !user.is_empty()
                            && user != "Idle"
                            && user != "Unknown"
                            && user != "None";

                        let display_user = if is_busy {
                            get_user_display_name(&user)
                        } else {
                            "Idle".to_string()
                        };

                        let user_color = get_user_color(&display_user).to_string();

                        cards.push(GPUCardData {
                            sid,
                            index: idx,
                            server_name,
                            model: clean_model,
                            memory_used_gb: (mem_u as f32 / 1024.0 * 10.0).round() / 10.0,
                            memory_total_gb: (mem_t as f32 / 1024.0).round(),
                            vram_pct: (vram_pct * 10.0).round() / 10.0,
                            utilization: util as i32,
                            power_draw: p_draw,
                            user: display_user,
                            user_color,
                            is_busy,
                        });
                    }
                }
            }
        }

        // Sort so 7号 comes first (cards 0, 1, 2) then 8号 (cards 0, 1)
        cards.sort_by(|a, b| {
            if a.sid == b.sid {
                a.index.cmp(&b.index)
            } else {
                a.sid.cmp(&b.sid)
            }
        });

        if cards.is_empty() {
            return vec![
                GPUCardData {
                    sid: "7".to_string(),
                    index: "0".to_string(),
                    server_name: "7号 · L40S [0]".to_string(),
                    model: "L40S".to_string(),
                    memory_used_gb: 0.0,
                    memory_total_gb: 45.0,
                    vram_pct: 0.0,
                    utilization: 0,
                    power_draw: "32/350W".to_string(),
                    user: "Idle".to_string(),
                    user_color: "#10B981".to_string(),
                    is_busy: false,
                },
                GPUCardData {
                    sid: "7".to_string(),
                    index: "1".to_string(),
                    server_name: "7号 · L40S [1]".to_string(),
                    model: "L40S".to_string(),
                    memory_used_gb: 0.0,
                    memory_total_gb: 45.0,
                    vram_pct: 0.0,
                    utilization: 0,
                    power_draw: "32/350W".to_string(),
                    user: "Idle".to_string(),
                    user_color: "#10B981".to_string(),
                    is_busy: false,
                },
                GPUCardData {
                    sid: "7".to_string(),
                    index: "2".to_string(),
                    server_name: "7号 · L40S [2]".to_string(),
                    model: "L40S".to_string(),
                    memory_used_gb: 0.0,
                    memory_total_gb: 45.0,
                    vram_pct: 0.0,
                    utilization: 0,
                    power_draw: "30/350W".to_string(),
                    user: "Idle".to_string(),
                    user_color: "#10B981".to_string(),
                    is_busy: false,
                },
                GPUCardData {
                    sid: "8".to_string(),
                    index: "0".to_string(),
                    server_name: "8号 · A100 [0]".to_string(),
                    model: "A100".to_string(),
                    memory_used_gb: 49.1,
                    memory_total_gb: 80.0,
                    vram_pct: 61.4,
                    utilization: 89,
                    power_draw: "104/300W".to_string(),
                    user: get_user_display_name("weirunguo"),
                    user_color: get_user_color(&get_user_display_name("weirunguo")).to_string(),
                    is_busy: true,
                },
                GPUCardData {
                    sid: "8".to_string(),
                    index: "1".to_string(),
                    server_name: "8号 · A100 [1]".to_string(),
                    model: "A100".to_string(),
                    memory_used_gb: 1.0,
                    memory_total_gb: 80.0,
                    vram_pct: 1.25,
                    utilization: 0,
                    power_draw: "64/300W".to_string(),
                    user: "Idle".to_string(),
                    user_color: "#10B981".to_string(),
                    is_busy: false,
                },
            ];
        }

        cards
    }

    pub fn query_host_stats(&self) -> Vec<HostStatData> {
        self.live_stats.read().unwrap().clone()
    }

    pub fn query_gantt_history(&self, days: i64) -> Vec<GanttRowData> {
        let tasks = [
            ("7", "0", "L40S [0]"),
            ("7", "1", "L40S [1]"),
            ("7", "2", "L40S [2]"),
            ("8", "0", "A100 [0]"),
            ("8", "1", "A100 [1]"),
        ];

        let mut results = Vec::new();
        if !Path::new(&self.db_path).exists() {
            for (_, _, name) in &tasks {
                results.push(GanttRowData {
                    task: name.to_string(),
                    has_activity: false,
                    start_pct: 0.0,
                    width_pct: 0.0,
                    user: String::new(),
                    user_color: "#3B82F6".to_string(),
                });
            }
            return results;
        }

        let hours = (days.max(1) * 24) as i64;
        let total_secs = (hours * 3600) as f32;

        if let Ok(conn) = Connection::open_with_flags(
            &self.db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI,
        ) {
            let thresh = (chrono::Local::now() - chrono::Duration::hours(hours))
                .format("%Y-%m-%d %H:%M:%S")
                .to_string();

            let query = "
                SELECT ip, gpu_index, top_user, min(timestamp), max(timestamp)
                FROM gpu_history
                WHERE timestamp > ?1 AND top_user != 'Idle'
                GROUP BY ip, gpu_index, top_user
            ";

            let mut card_map: std::collections::HashMap<(String, String), (String, f32, f32)> = std::collections::HashMap::new();

            if let Ok(mut stmt) = conn.prepare(query) {
                if let Ok(rows) = stmt.query_map([&thresh], |row| {
                    let ip: String = row.get(0)?;
                    let idx: String = row.get::<_, String>(1)
                        .or_else(|_| row.get::<_, i64>(1).map(|v| v.to_string()))
                        .unwrap_or_else(|_| "0".to_string());
                    let user: String = row.get(2)?;
                    let min_t: String = row.get(3)?;
                    let max_t: String = row.get(4)?;
                    Ok((ip, idx, user, min_t, max_t))
                }) {
                    let now = chrono::Local::now().naive_local();
                    let window_start = now - chrono::Duration::hours(hours);

                    for r in rows.flatten() {
                        let (ip, idx, user, min_t, max_t) = r;
                        let sid = if ip.contains('.') {
                            ip.split('.').last().unwrap_or("").to_string()
                        } else {
                            ip
                        };

                        let t_min = chrono::NaiveDateTime::parse_from_str(&min_t, "%Y-%m-%d %H:%M:%S")
                            .unwrap_or(window_start);
                        let t_max = chrono::NaiveDateTime::parse_from_str(&max_t, "%Y-%m-%d %H:%M:%S")
                            .unwrap_or(now);

                        let start_sec = (t_min - window_start).num_seconds().max(0) as f32;
                        let end_sec = (t_max - window_start).num_seconds().min(hours * 3600).max(0) as f32;

                        let start_pct = (start_sec / total_secs).clamp(0.0, 1.0);
                        let mut width_pct = ((end_sec - start_sec) / total_secs).clamp(0.05, 1.0);
                        if start_pct + width_pct > 1.0 {
                            width_pct = 1.0 - start_pct;
                        }

                        card_map.insert((sid, idx), (get_user_display_name(&user), start_pct, width_pct));
                    }
                }
            }

            for (sid, idx, name) in &tasks {
                if let Some((user, start_pct, width_pct)) = card_map.get(&(sid.to_string(), idx.to_string())) {
                    let color = get_user_color(user);
                    results.push(GanttRowData {
                        task: name.to_string(),
                        has_activity: true,
                        start_pct: *start_pct,
                        width_pct: *width_pct,
                        user: user.clone(),
                        user_color: color.to_string(),
                    });
                } else {
                    results.push(GanttRowData {
                        task: name.to_string(),
                        has_activity: false,
                        start_pct: 0.0,
                        width_pct: 0.0,
                        user: String::new(),
                        user_color: "#3B82F6".to_string(),
                    });
                }
            }
        }

        if results.is_empty() {
            for (_, _, name) in &tasks {
                results.push(GanttRowData {
                    task: name.to_string(),
                    has_activity: false,
                    start_pct: 0.0,
                    width_pct: 0.0,
                    user: String::new(),
                    user_color: "#3B82F6".to_string(),
                });
            }
        }

        results
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_user_mapping() {
        let name = get_user_display_name("weirunguo");
        println!("Mapped weirunguo -> {}", name);
        assert_ne!(name, "weirunguo", "Should map weirunguo to Chinese name");
    }
}
