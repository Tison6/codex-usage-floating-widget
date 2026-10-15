use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::path::Path;

pub const DB_FILE: &str = r"D:/gpu_history.db";

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
    pub is_online: bool,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GanttInterval {
    pub sid: String,
    pub task: String,
    pub user: String,
    pub start_ts: i64,
    pub end_ts: i64,
}

pub struct ServerManager {
    db_path: String,
}

impl ServerManager {
    pub fn new() -> Self {
        Self {
            db_path: DB_FILE.to_string(),
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
                            user,
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
                    user: "魏**".to_string(),
                    is_busy: true,
                },
                GPUCardData {
                    sid: "8".to_string(),
                    index: "1".to_string(),
                    server_name: "8号 · A100 [1]".to_string(),
                    model: "A100".to_string(),
                    memory_used_gb: 0.0,
                    memory_total_gb: 80.0,
                    vram_pct: 0.0,
                    utilization: 0,
                    power_draw: "64/300W".to_string(),
                    user: "Idle".to_string(),
                    is_busy: false,
                },
            ];
        }

        cards
    }

    pub fn query_host_stats(&self) -> Vec<HostStatData> {
        vec![
            HostStatData {
                id: "gpu7".to_string(),
                name: "GPU 7号 · L40S".to_string(),
                cpu_pct: 2.0,
                mem_used_gb: 62.9,
                mem_total_gb: 252.0,
                mem_pct: 25.0,
                disk_free_gb: 5.0,
                is_online: true,
            },
            HostStatData {
                id: "gpu8".to_string(),
                name: "GPU 8号 · A100".to_string(),
                cpu_pct: 4.0,
                mem_used_gb: 78.4,
                mem_total_gb: 503.0,
                mem_pct: 15.6,
                disk_free_gb: 280.0,
                is_online: true,
            },
            HostStatData {
                id: "quad".to_string(),
                name: "quad".to_string(),
                cpu_pct: 12.5,
                mem_used_gb: 18.0,
                mem_total_gb: 64.0,
                mem_pct: 28.1,
                disk_free_gb: 340.0,
                is_online: true,
            },
            HostStatData {
                id: "e5".to_string(),
                name: "e5".to_string(),
                cpu_pct: 5.2,
                mem_used_gb: 14.0,
                mem_total_gb: 32.0,
                mem_pct: 43.8,
                disk_free_gb: 210.0,
                is_online: true,
            },
            HostStatData {
                id: "8375c".to_string(),
                name: "8375c".to_string(),
                cpu_pct: 24.0,
                mem_used_gb: 42.0,
                mem_total_gb: 128.0,
                mem_pct: 32.8,
                disk_free_gb: 850.0,
                is_online: true,
            },
        ]
    }
}
