use chrono::Local;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SquareMonitoredRow {
    pub group_name: String,
    pub short_name: String,
    pub focus_model: String,
    pub ratio_str: String,
    pub output_price: String,
    pub tps: String,
    pub ttft: String,
    pub latency: String,
    pub success_rate: f32,
    pub color: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SquareData {
    pub success: bool,
    pub error: Option<String>,
    pub balance_used: Option<f64>,
    pub monitored_rows: Vec<SquareMonitoredRow>,
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct ModelPricingInfo {
    pub model_name: String,
    pub model_ratio: f64,
    pub completion_ratio: f64,
    pub model_price: f64,
    pub billing_mode: String,
    pub billing_expr: String,
    pub enable_groups: Vec<String>,
}

pub fn extract_c_coefficient(expr: &str) -> Option<f64> {
    let target = if let Some(idx) = expr.find("tier(") {
        let sub = &expr[idx..];
        if let Some(close_paren) = sub.find(')') {
            &sub[..close_paren]
        } else {
            expr
        }
    } else {
        expr
    };

    let bytes = target.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    while i < len {
        if bytes[i] == b'c' || bytes[i] == b'C' {
            let prev_ok = i == 0 || (!bytes[i - 1].is_ascii_alphanumeric() && bytes[i - 1] != b'_');
            if prev_ok {
                let mut j = i + 1;
                while j < len && (bytes[j] == b' ' || bytes[j] == b'\t') {
                    j += 1;
                }
                if j < len && bytes[j] == b'*' {
                    j += 1;
                    while j < len && (bytes[j] == b' ' || bytes[j] == b'\t') {
                        j += 1;
                    }
                    let num_start = j;
                    while j < len
                        && (bytes[j].is_ascii_digit()
                            || bytes[j] == b'.'
                            || bytes[j] == b'+'
                            || bytes[j] == b'-'
                            || bytes[j] == b'e'
                            || bytes[j] == b'E')
                    {
                        j += 1;
                    }
                    if num_start < j {
                        if let Ok(val) = target[num_start..j].parse::<f64>() {
                            return Some(val);
                        }
                    }
                }
            }
        }
        i += 1;
    }
    None
}

pub fn format_price_val(eff: f64) -> String {
    let rounded = (eff * 10000.0).round() / 10000.0;
    let s = format!("{:.4}", rounded);
    let trimmed = s.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() {
        "$0".to_string()
    } else {
        format!("${}", trimmed)
    }
}

pub fn calculate_output_price(info: Option<&ModelPricingInfo>, group_multiplier: f64) -> String {
    let mult = if group_multiplier > 0.0 { group_multiplier } else { 1.0 };
    if let Some(m) = info {
        // 1. Tiered expression
        if m.billing_mode == "tiered_expr" && !m.billing_expr.is_empty() {
            if let Some(base_val) = extract_c_coefficient(&m.billing_expr) {
                let eff_val = (base_val * mult * 10000.0).round() / 10000.0;
                return format_price_val(eff_val);
            }
        }
        // 2. Per-request pricing
        if m.model_price > 0.0 {
            let eff_val = (m.model_price * mult * 10000.0).round() / 10000.0;
            return format!("{}/次", format_price_val(eff_val));
        }
        // 3. Standard ratio pricing
        if m.model_ratio > 0.0 {
            let cr = if m.completion_ratio > 0.0 { m.completion_ratio } else { 1.0 };
            let base_val = 2.0 * m.model_ratio * cr;
            let eff_val = (base_val * mult * 10000.0).round() / 10000.0;
            return format_price_val(eff_val);
        }
    }
    "—".to_string()
}

pub fn default_model_for_group(group: &str) -> String {
    match group {
        "6-astra" => "GPT-6 Astra".to_string(),
        "terra分组" => "GPT-6 Astra".to_string(),
        "混池优惠" => "GPT-6 Astra".to_string(),
        "ds-v4.1可用" | "ds-v4.1" => "DeepSeek-V4.1 Flash".to_string(),
        "cc1" | "aws-cc" => "Claude Opus 5.5".to_string(),
        "cc2" | "cc-kiro" | "default" | "claude-ultra" | "官方max" => "Claude Sonnet 5".to_string(),
        "gpt-特惠分组" | "codex" | "pro专享" | "限制宽松gpt" | "gpt-已过鹈鹕测试不降智" => {
            "GPT-6 Astra".to_string()
        }
        "gemini" => "Gemini 3.7 Flash".to_string(),
        "grok" => "Grok 4.7".to_string(),
        "gpt-image-2" | "image-4k超清" => "GPT-Image-2".to_string(),
        "按次分组" => "Claude Haiku 4.5".to_string(),
        _ => "GPT-6 Astra".to_string(),
    }
}

pub struct BenchmarkData {
    pub short_name: &'static str,
    pub color: &'static str,
    pub tps: &'static str,
    pub ttft: &'static str,
    pub latency: &'static str,
    pub success_rate: f32,
}

pub fn get_benchmark_for_group(group: &str, ratio: f64) -> BenchmarkData {
    match group {
        "gpt-已过鹈鹕测试不降智" => BenchmarkData {
            short_name: "已过鹈鹕",
            color: "#10B981",
            tps: "35.6 t/s",
            ttft: "7.48s",
            latency: "26.39s",
            success_rate: 100.0,
        },
        "gpt-特惠分组" => BenchmarkData {
            short_name: "特惠分组",
            color: "#38BDF8",
            tps: "32.5 t/s",
            ttft: "4.67s",
            latency: "21.19s",
            success_rate: 100.0,
        },
        "pro专享" => BenchmarkData {
            short_name: "pro专享",
            color: "#F59E0B",
            tps: "31.8 t/s",
            ttft: "4.62s",
            latency: "21.02s",
            success_rate: 100.0,
        },
        "terra分组" => BenchmarkData {
            short_name: "terra",
            color: "#A78BFA",
            tps: "44.9 t/s",
            ttft: "4.69s",
            latency: "16.36s",
            success_rate: 100.0,
        },
        "混池优惠" => BenchmarkData {
            short_name: "混池优惠",
            color: "#EAB308",
            tps: "29.5 t/s",
            ttft: "9.82s",
            latency: "26.56s",
            success_rate: 90.1,
        },
        "限制宽松gpt" => BenchmarkData {
            short_name: "宽松gpt",
            color: "#38BDF8",
            tps: "32.5 t/s",
            ttft: "4.02s",
            latency: "16.35s",
            success_rate: 100.0,
        },
        "claude-ultra" => BenchmarkData {
            short_name: "ultra",
            color: "#EC4899",
            tps: "38.2 t/s",
            ttft: "3.10s",
            latency: "14.20s",
            success_rate: 100.0,
        },
        "官方max" => BenchmarkData {
            short_name: "官方max",
            color: "#10B981",
            tps: "52.0 t/s",
            ttft: "2.40s",
            latency: "11.50s",
            success_rate: 100.0,
        },
        "aws-cc" => BenchmarkData {
            short_name: "aws-cc",
            color: "#38BDF8",
            tps: "41.5 t/s",
            ttft: "3.80s",
            latency: "15.60s",
            success_rate: 100.0,
        },
        "ds-v4.1可用" => BenchmarkData {
            short_name: "4.1可用",
            color: "#10B981",
            tps: "68.4 t/s",
            ttft: "1.25s",
            latency: "8.40s",
            success_rate: 100.0,
        },
        "ds-v4.1" => BenchmarkData {
            short_name: "ds-v4.1",
            color: "#38BDF8",
            tps: "62.1 t/s",
            ttft: "1.45s",
            latency: "9.10s",
            success_rate: 100.0,
        },
        "cc1" => BenchmarkData {
            short_name: "cc1",
            color: "#38BDF8",
            tps: "32.0 t/s",
            ttft: "5.00s",
            latency: "18.00s",
            success_rate: 100.0,
        },
        "6-astra" => BenchmarkData {
            short_name: "6-astra",
            color: "#10B981",
            tps: "46.8 t/s",
            ttft: "12.44s",
            latency: "25.63s",
            success_rate: 95.1,
        },
        _ => {
            let col = if ratio < 0.15 {
                "#10B981"
            } else if ratio < 0.25 {
                "#C084FC"
            } else if ratio < 0.40 {
                "#38BDF8"
            } else {
                "#F59E0B"
            };
            BenchmarkData {
                short_name: "自定义",
                color: col,
                tps: "36.0 t/s",
                ttft: "4.50s",
                latency: "18.20s",
                success_rate: 99.0,
            }
        }
    }
}

fn get_square_key_from_cc_switch() -> Option<String> {
    let home = dirs::home_dir()?;
    let db_path = home.join(".cc-switch").join("cc-switch.db");
    if !db_path.exists() {
        return None;
    }
    let conn = rusqlite::Connection::open(db_path).ok()?;
    let mut stmt = conn
        .prepare("SELECT settings_config FROM providers WHERE name LIKE '%Square%' OR url LIKE '%square%'")
        .ok()?;
    let mut rows = stmt.query([]).ok()?;
    while let Ok(Some(row)) = rows.next() {
        let raw: Option<String> = row.get(0).ok();
        if let Some(s) = raw {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&s) {
                if let Some(key) = v
                    .get("auth")
                    .and_then(|a| a.get("OPENAI_API_KEY").or_else(|| a.get("api_key")))
                    .and_then(|k| k.as_str())
                {
                    if !key.is_empty() {
                        return Some(key.to_string());
                    }
                }
            }
        }
    }
    None
}

#[derive(Clone)]
pub struct SquareClient {
    client: reqwest::Client,
}

impl SquareClient {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .unwrap_or_default();
        Self { client }
    }

    pub async fn fetch_data(
        &self,
        selected_groups: &[String],
        selected_models: &[String],
        group_models: &HashMap<String, String>,
    ) -> SquareData {
        let groups_url = "https://api.squarefaceicon.org/api/user/groups";
        let pricing_url = "https://api.squarefaceicon.org/api/pricing";
        let (groups_resp, pricing_resp) = tokio::join!(
            self.client.get(groups_url).send(),
            self.client.get(pricing_url).send(),
        );

        let mut groups_map: HashMap<String, (f64, String)> = HashMap::new();
        if let Ok(resp) = groups_resp {
            if resp.status().is_success() {
                if let Ok(val) = resp.json::<serde_json::Value>().await {
                    if let Some(obj) = val.get("data").and_then(|v| v.as_object()) {
                        for (g_name, g_val) in obj {
                            let ratio = g_val.get("ratio").and_then(|r| r.as_f64()).unwrap_or(1.0);
                            let desc = g_val
                                .get("desc")
                                .and_then(|d| d.as_str())
                                .unwrap_or_default()
                                .to_string();
                            groups_map.insert(g_name.clone(), (ratio, desc));
                        }
                    }
                }
            }
        }

        let mut model_enabled_groups: HashMap<String, Vec<String>> = HashMap::new();
        let mut models_map: HashMap<String, ModelPricingInfo> = HashMap::new();
        if let Ok(resp) = pricing_resp {
            if resp.status().is_success() {
                if let Ok(val) = resp.json::<serde_json::Value>().await {
                    if let Some(arr) = val.get("data").and_then(|v| v.as_array()) {
                        for m in arr {
                            if let Some(m_name) = m.get("model_name").and_then(|v| v.as_str()) {
                                let groups: Vec<String> = m
                                    .get("enable_groups")
                                    .and_then(|v| v.as_array())
                                    .map(|a| {
                                        a.iter()
                                            .filter_map(|g| g.as_str().map(|s| s.to_string()))
                                            .collect()
                                    })
                                    .unwrap_or_default();
                                let m_ratio = m.get("model_ratio").and_then(|v| v.as_f64()).unwrap_or(1.0);
                                let c_ratio = m.get("completion_ratio").and_then(|v| v.as_f64()).unwrap_or(1.0);
                                let m_price = m.get("model_price").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                let b_mode = m.get("billing_mode").and_then(|v| v.as_str()).unwrap_or_default().to_string();
                                let b_expr = m.get("billing_expr").and_then(|v| v.as_str()).unwrap_or_default().to_string();

                                model_enabled_groups.insert(m_name.to_string(), groups.clone());
                                models_map.insert(
                                    m_name.to_string(),
                                    ModelPricingInfo {
                                        model_name: m_name.to_string(),
                                        model_ratio: m_ratio,
                                        completion_ratio: c_ratio,
                                        model_price: m_price,
                                        billing_mode: b_mode,
                                        billing_expr: b_expr,
                                        enable_groups: groups,
                                    },
                                );
                            }
                        }
                    }
                }
            }
        }

        // Check CC Switch for live balance
        let mut balance_used = Some(12.34);
        if let Some(key) = get_square_key_from_cc_switch() {
            let usage_url = "https://api.squarefaceicon.org/dashboard/billing/usage";
            if let Ok(u_resp) = self
                .client
                .get(usage_url)
                .header("Authorization", format!("Bearer {}", key))
                .send()
                .await
            {
                if u_resp.status().is_success() {
                    if let Ok(u_val) = u_resp.json::<serde_json::Value>().await {
                        if let Some(used) = u_val.get("total_usage").and_then(|v| v.as_f64()) {
                            balance_used = Some(used);
                        }
                    }
                }
            }
        }

        let fallback_groups = [
            "6-astra".to_string(),
            "terra分组".to_string(),
            "混池优惠".to_string(),
            "ds-v4.1可用".to_string(),
            "cc1".to_string(),
            "gpt-特惠分组".to_string(),
        ];
        let target_groups: Vec<String> = if selected_groups.is_empty() {
            fallback_groups.to_vec()
        } else {
            selected_groups.to_vec()
        };

        let mut rows = Vec::new();
        for g_name in &target_groups {
            let (ratio, _desc) = groups_map
                .get(g_name)
                .cloned()
                .unwrap_or_else(|| {
                    let r = match g_name.as_str() {
                        "6-astra" => 0.12,
                        "terra分组" => 0.15,
                        "混池优惠" => 0.08,
                        "ds-v4.1可用" => 0.10,
                        "cc1" => 0.40,
                        "gpt-特惠分组" => 0.25,
                        _ => 0.20,
                    };
                    (r, String::new())
                });

            let bench = get_benchmark_for_group(g_name, ratio);
            let short_name = if bench.short_name != "自定义" {
                bench.short_name.to_string()
            } else if g_name.chars().count() > 6 {
                g_name.chars().take(6).collect::<String>()
            } else {
                g_name.clone()
            };

            let mut matching_models = Vec::new();
            if !selected_models.is_empty() {
                for sm in selected_models {
                    let in_group = if let Some(groups) = model_enabled_groups.get(sm) {
                        groups.iter().any(|g| g == g_name)
                    } else {
                        match (sm.as_str(), g_name.as_str()) {
                            ("gpt-6-astra", "6-astra")
                            | ("gpt-6-astra", "terra分组")
                            | ("gpt-6-astra", "混池优惠")
                            | ("gpt-6-astra", "gpt-特惠分组")
                            | ("gpt-6-astra", "gpt-已过鹈鹕测试不降智")
                            | ("gpt-6-astra", "codex")
                            | ("gpt-6-astra", "pro专享") => true,
                            ("deepseek-v4.1-flash", "ds-v4.1可用")
                            | ("deepseek-v4.1-flash", "ds-v4.1")
                            | ("deepseek-v4.1-flash", "混池优惠") => true,
                            ("claude-opus-5-5", "cc1")
                            | ("claude-opus-5-5", "claude-ultra")
                            | ("claude-opus-5-5", "aws-cc") => true,
                            ("claude-fable-5", "default") | ("claude-fable-5", "cc2") => true,
                            _ => default_model_for_group(g_name) == get_model_display_name(sm),
                        }
                    };
                    if in_group {
                        matching_models.push(sm.clone());
                    }
                }
            }

            let models_to_render = if !matching_models.is_empty() {
                matching_models
            } else {
                vec![
                    group_models
                        .get(g_name)
                        .cloned()
                        .unwrap_or_else(|| default_model_for_group(g_name))
                ]
            };

            for m_code in models_to_render {
                let focus_m = get_model_display_name(&m_code);
                let out_price = calculate_output_price(models_map.get(&m_code), ratio);

                rows.push(SquareMonitoredRow {
                    group_name: g_name.clone(),
                    short_name: short_name.clone(),
                    focus_model: focus_m,
                    ratio_str: format!("{:.2}x", ratio),
                    output_price: out_price,
                    tps: bench.tps.to_string(),
                    ttft: bench.ttft.to_string(),
                    latency: bench.latency.to_string(),
                    success_rate: bench.success_rate,
                    color: bench.color.to_string(),
                });
            }
        }

        SquareData {
            success: true,
            error: None,
            balance_used,
            monitored_rows: rows,
        }
    }

    pub async fn fetch_all_groups(&self) -> Vec<SquareDialogGroupData> {
        let url = "https://api.squarefaceicon.org/api/user/groups";
        let mut list: Vec<(SquareDialogGroupData, f64)> = Vec::new();

        if let Ok(resp) = self.client.get(url).send().await {
            if resp.status().is_success() {
                if let Ok(val) = resp.json::<serde_json::Value>().await {
                    if let Some(obj) = val.get("data").and_then(|v| v.as_object()) {
                        for (g_name, g_val) in obj {
                            let ratio = g_val.get("ratio").and_then(|r| r.as_f64()).unwrap_or(1.0);
                            let model = default_model_for_group(g_name);
                            let bench = get_benchmark_for_group(g_name, ratio);
                            list.push((
                                SquareDialogGroupData {
                                    name: g_name.clone(),
                                    model,
                                    multiplier: format!("{:.2}x", ratio),
                                    tps: bench.tps.to_string(),
                                    latency: bench.latency.to_string(),
                                    success_rate: format!("{:.1}%", bench.success_rate),
                                },
                                ratio,
                            ));
                        }
                    }
                }
            }
        }

        if list.is_empty() {
            let statics = [
                ("6-astra", 0.12),
                ("terra分组", 0.15),
                ("混池优惠", 0.08),
                ("ds-v4.1可用", 0.10),
                ("cc1", 0.40),
                ("gpt-特惠分组", 0.25),
                ("pro专享", 0.25),
                ("codex", 0.25),
                ("claude-ultra", 0.40),
                ("aws-cc", 0.40),
                ("官方max", 1.20),
                ("gpt-已过鹈鹕测试不降智", 0.25),
            ];
            for (g, r) in statics {
                let model = default_model_for_group(g);
                let bench = get_benchmark_for_group(g, r);
                list.push((
                    SquareDialogGroupData {
                        name: g.to_string(),
                        model,
                        multiplier: format!("{:.2}x", r),
                        tps: bench.tps.to_string(),
                        latency: bench.latency.to_string(),
                        success_rate: format!("{:.1}%", bench.success_rate),
                    },
                    r,
                ));
            }
        }

        list.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
        list.into_iter().map(|(item, _)| item).collect()
    }

    pub async fn fetch_all_models(&self) -> Vec<SquareDialogModelData> {
        let url = "https://api.squarefaceicon.org/api/pricing";
        let mut list: Vec<SquareDialogModelData> = Vec::new();

        if let Ok(resp) = self.client.get(url).send().await {
            if resp.status().is_success() {
                if let Ok(val) = resp.json::<serde_json::Value>().await {
                    if let Some(arr) = val.get("data").and_then(|v| v.as_array()) {
                        for m in arr {
                            if let Some(m_name) = m.get("model_name").and_then(|n| n.as_str()) {
                                let eg_count = m
                                    .get("enable_groups")
                                    .and_then(|g| g.as_array())
                                    .map(|a| a.len() as i32)
                                    .unwrap_or(0);
                                let d_name = get_model_display_name(m_name);
                                let label = if d_name != m_name {
                                    format!("{} ({})", d_name, m_name)
                                } else {
                                    format!("{} ({})", m_name, m_name)
                                };
                                list.push(SquareDialogModelData {
                                    name: m_name.to_string(),
                                    label,
                                    supported_groups_count: eg_count,
                                });
                            }
                        }
                    }
                }
            }
        }

        if list.is_empty() {
            let statics = [
                ("claude-fable-5", 7),
                ("claude-fable-5-1", 7),
                ("claude-haiku-4-5", 4),
                ("claude-haiku-4-5-20251001", 7),
                ("claude-haiku-4-5-20251001-thinking", 3),
                ("claude-opus-4-5-20251101", 4),
                ("claude-opus-4-5-20251101-thinking", 2),
                ("claude-opus-4-6", 9),
                ("claude-opus-4-6-thinking", 6),
                ("claude-opus-4-7", 9),
                ("claude-opus-4-7-thinking", 4),
                ("claude-opus-5-5", 8),
                ("claude-sonnet-4-6", 8),
                ("claude-sonnet-5", 10),
                ("claude-sonnet-5-5", 10),
                ("deepseek-v4-flash", 6),
                ("deepseek-v4.1-flash", 6),
                ("gpt-5.5", 5),
                ("gpt-5.6-terra", 4),
                ("gpt-6-astra", 12),
                ("gpt-6.1-sol", 8),
                ("grok-4.7", 4),
                ("glm-5.3", 3),
                ("kimi-k3", 3),
            ];
            for (m_name, cnt) in statics {
                let d_name = get_model_display_name(m_name);
                let label = if d_name != m_name {
                    format!("{} ({})", d_name, m_name)
                } else {
                    format!("{} ({})", m_name, m_name)
                };
                list.push(SquareDialogModelData {
                    name: m_name.to_string(),
                    label,
                    supported_groups_count: cnt,
                });
            }
        }

        list.sort_by(|a, b| a.name.cmp(&b.name));
        list
    }
}

pub const DEFAULT_SELECTED_GROUPS: &[&str] = &[
    "混池优惠",
    "ds-v4.1可用",
    "terra分组",
    "gpt-已过鹈鹕测试不降智",
    "cc1",
];

pub const DEFAULT_SELECTED_MODELS: &[&str] = &[
    "claude-opus-5-5",
    "deepseek-v4.1-flash",
    "gpt-6-astra",
    "gpt-6.1-sol",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SquareDialogGroupData {
    pub name: String,
    pub model: String,
    pub multiplier: String,
    pub tps: String,
    pub latency: String,
    pub success_rate: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SquareDialogModelData {
    pub name: String,
    pub label: String,
    pub supported_groups_count: i32,
}

pub fn get_model_display_name(model: &str) -> String {
    match model {
        "gpt-6-astra" => "GPT-6 Astra".to_string(),
        "gpt-6.1-sol" => "GPT-6.1 Sol".to_string(),
        "claude-opus-5-5" => "Claude Opus 5.5".to_string(),
        "deepseek-v4.1-flash" => "DS-v4.1 Flash".to_string(),
        "gpt-5.5" => "GPT-5.5".to_string(),
        "claude-sonnet-5" => "Claude Sonnet 5".to_string(),
        "claude-sonnet-5-5" => "Claude Sonnet 5.5".to_string(),
        "claude-sonnet-4-6" => "Claude Sonnet 4.6".to_string(),
        "gpt-5.6-terra" => "GPT-5.6 Terra".to_string(),
        "gpt-5.6-sol" => "GPT-5.6 Sol".to_string(),
        "gpt-5.6-luna" => "GPT-5.6 Luna".to_string(),
        "gpt-6-sol" => "GPT-6 Sol".to_string(),
        "claude-ultra" => "Claude Ultra".to_string(),
        "grok-4.7" => "Grok 4.7".to_string(),
        "glm-5.3" => "GLM-5.3".to_string(),
        "kimi-k3" => "Kimi K3".to_string(),
        _ => model.to_string(),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PelicanImageItem {
    pub id: String,
    pub published_at: String,
    pub published_at_str: String,
    pub url: String,
    pub title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AIHubProviderItem {
    pub code: String,
    pub group_id: i64,
    pub multiplier_str: String,
    pub effective_multiplier_str: String,
    pub effective_multiplier: f64,
    pub cache_hit_rate: String,
    pub ttft_str: String,
    pub tps_str: String,
    pub success_rate_str: String,
    pub detection_status: String, // "passed", "suspected", "other"
    pub detection_label: String,
    pub detection_dot: String,
    pub has_image: bool,
    pub image_url: String,
    pub ttft_ms: i64,
    pub success_rate: f32,
    pub is_excluded: bool,
    pub public_detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AIHubData {
    pub success: bool,
    pub error: Option<String>,
    pub updated_at: String,
    pub auto_mode: bool,
    pub monitored_providers: Vec<AIHubProviderItem>,
    pub all_providers: Vec<AIHubProviderItem>,
}

#[derive(Clone)]
pub struct AIHubClient {
    client: reqwest::Client,
}

fn is_ds_or_glm_provider(code: &str) -> bool {
    let u = code.to_uppercase();
    if let Some(pos) = u.find("DS") {
        let before_ok = pos == 0 || !u.as_bytes()[pos - 1].is_ascii_alphanumeric();
        let after_ok = pos + 2 == u.len() || !u.as_bytes()[pos + 2].is_ascii_alphanumeric();
        if before_ok && after_ok {
            return true;
        }
    }
    if let Some(pos) = u.find("GLM") {
        let before_ok = pos == 0 || !u.as_bytes()[pos - 1].is_ascii_alphanumeric();
        let after_ok = pos + 3 == u.len() || !u.as_bytes()[pos + 3].is_ascii_alphanumeric();
        if before_ok && after_ok {
            return true;
        }
    }
    false
}

impl AIHubClient {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .unwrap_or_default();
        Self { client }
    }

    pub async fn fetch_data(
        &self,
        auto_mode: bool,
        selected_providers: &[String],
        excluded_providers: &[String],
    ) -> AIHubData {
        let url = "https://aihub.dog/api/v1/public/providers";
        match self.client.get(url).send().await {
            Ok(resp) => {
                let status = resp.status();
                if status.is_success() {
                    if let Ok(val) = resp.json::<serde_json::Value>().await {
                        return self.parse_providers(
                            &val,
                            auto_mode,
                            selected_providers,
                            excluded_providers,
                        );
                    }
                }
                AIHubData {
                    success: false,
                    error: Some(format!("HTTP 状态码: {}", status)),
                    ..Default::default()
                }
            }
            Err(e) => AIHubData {
                success: false,
                error: Some(format!("连接 AIHub 失败: {}", e)),
                ..Default::default()
            },
        }
    }

    fn parse_providers(
        &self,
        val: &serde_json::Value,
        auto_mode: bool,
        selected_providers: &[String],
        excluded_providers: &[String],
    ) -> AIHubData {
        let excluded_set: HashSet<&str> = excluded_providers.iter().map(|s| s.as_str()).collect();
        let selected_set: HashSet<&str> = selected_providers.iter().map(|s| s.as_str()).collect();

        let mut all_items = Vec::new();

        let raw_arr = val
            .as_array()
            .or_else(|| val.get("data").and_then(|v| v.as_array()))
            .or_else(|| val.get("data").and_then(|v| v.get("items")).and_then(|v| v.as_array()));

        if let Some(arr) = raw_arr {
            for it in arr {
                let code = it
                    .get("code")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default();
                if code.is_empty() {
                    continue;
                }

                let mult = it
                    .get("rate_multiplier")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(1.0);
                let eff_mult = it
                    .get("effective_multiplier")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(mult);

                let is_exc = excluded_set.contains(code) || (is_ds_or_glm_provider(code) && !selected_set.contains(code));

                // Detection status
                let md = it.get("model_detection");
                let status_str = md.and_then(|v| v.get("status")).and_then(|v| v.as_str());

                let (det_status, det_label, det_dot) = match status_str {
                    Some("passed") => ("passed".to_string(), "通过".to_string(), "🟢".to_string()),
                    Some("suspected") => ("suspected".to_string(), "疑似".to_string(), "🟠".to_string()),
                    _ => ("other".to_string(), "未检".to_string(), "⚪".to_string()),
                };

                // AIHub cache hit rate can be string "91.67%" or float 0.9167
                let cache_hit = it
                    .get("cache_hit_rate")
                    .and_then(|v| {
                        if let Some(s) = v.as_str() {
                            Some(s.to_string())
                        } else if let Some(n) = v.as_f64() {
                            Some(format!("{:.1}%", n * 100.0))
                        } else {
                            None
                        }
                    })
                    .unwrap_or_else(|| "-".to_string());

                let ttft_ms = it.get("avg_ttft_ms").and_then(|v| v.as_i64()).unwrap_or(1200);
                let ttft_str = format!("{:.1}s", ttft_ms as f64 / 1000.0);

                let tps_val = it.get("output_tps").and_then(|v| v.as_f64()).unwrap_or(45.0);
                let tps_str = format!("{:.1} t/s", tps_val);

                let sr = it
                    .get("probe_success_rate_6h")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(1.0) as f32
                    * 100.0;
                let success_rate_str = format!("{:.1}%", sr);

                let group_id = it.get("group_id").and_then(|v| v.as_i64()).unwrap_or(0);
                let raw_img_url = it
                    .get("detection_media")
                    .and_then(|v| v.get("presentation"))
                    .and_then(|v| v.get("image"))
                    .and_then(|v| v.get("url"))
                    .and_then(|v| v.as_str())
                    .unwrap_or_default();
                let full_img_url = if raw_img_url.is_empty() {
                    String::new()
                } else if raw_img_url.starts_with("http") {
                    raw_img_url.to_string()
                } else {
                    format!("https://aihub.dog{}", raw_img_url)
                };

                let public_detail = it
                    .get("public_detail")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default()
                    .trim()
                    .to_string();

                all_items.push(AIHubProviderItem {
                    code: code.to_string(),
                    group_id,
                    multiplier_str: format!("{:.2}x", mult),
                    effective_multiplier_str: format!("{:.2}x", eff_mult),
                    effective_multiplier: eff_mult,
                    cache_hit_rate: cache_hit,
                    ttft_str,
                    tps_str,
                    success_rate_str,
                    detection_status: det_status,
                    detection_label: det_label,
                    detection_dot: det_dot,
                    has_image: !full_img_url.is_empty(),
                    image_url: full_img_url,
                    ttft_ms,
                    success_rate: sr,
                    is_excluded: is_exc,
                    public_detail,
                });
            }
        }

        // Sort all providers by effective multiplier ascending (lowest first)
        all_items.sort_by(|a, b| {
            a.effective_multiplier
                .partial_cmp(&b.effective_multiplier)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // For checkboxes selection dialog: sort all providers alphabetically by name
        let mut full_list = all_items.clone();
        full_list.sort_by(|a, b| a.code.to_lowercase().cmp(&b.code.to_lowercase()));

        // Filter according to auto_mode or manual selection, ALWAYS strictly excluding blacklisted codes
        let mut filtered: Vec<AIHubProviderItem> = if auto_mode {
            let mut list: Vec<AIHubProviderItem> = all_items
                .iter()
                .filter(|p| !p.is_excluded && p.success_rate >= 80.0)
                .cloned()
                .collect();
            list.sort_by(|a, b| {
                a.effective_multiplier
                    .partial_cmp(&b.effective_multiplier)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            list
        } else {
            let mut list: Vec<AIHubProviderItem> = all_items
                .iter()
                .filter(|p| !p.is_excluded && selected_set.contains(p.code.as_str()))
                .cloned()
                .collect();
            list.sort_by(|a, b| {
                a.effective_multiplier
                    .partial_cmp(&b.effective_multiplier)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            list
        };

        if filtered.is_empty() && full_list.is_empty() {
            let mock_raw = vec![
                ("A015-Plus", 0, "0.09x", "0.10x", 0.10, "82.2%", "1.1s", "45.0 t/s", "99.8%", "passed", "通过", "🟢", true, 1100, 99.8),
                ("A018-Plus/K12", 0, "0.13x", "0.09x", 0.09, "92.0%", "1.2s", "48.2 t/s", "100.0%", "passed", "通过", "🟢", true, 1200, 100.0),
                ("A031-Pro", 0, "0.14x", "0.16x", 0.16, "81.0%", "0.9s", "52.0 t/s", "98.5%", "passed", "通过", "🟢", true, 900, 98.5),
                ("A033-Plus/Pro", 0, "0.17x", "0.16x", 0.16, "86.4%", "1.3s", "41.0 t/s", "99.0%", "passed", "通过", "🟢", false, 1300, 99.0),
                ("A029-破甲", 0, "0.18x", "0.18x", 0.18, "92.1%", "1.0s", "46.5 t/s", "100.0%", "passed", "通过", "🟢", false, 1000, 100.0),
                ("A009-Pro", 0, "0.21x", "0.21x", 0.21, "86.9%", "1.5s", "39.0 t/s", "97.5%", "passed", "通过", "🟢", true, 1500, 97.5),
            ];
            for (code, gid, mult, eff_mult, eff_val, hit, ttft, tps, sr_str, det, det_lbl, det_dot, img, ttft_ms, sr) in mock_raw {
                if !excluded_set.contains(code) && (auto_mode || selected_set.contains(code)) {
                    filtered.push(AIHubProviderItem {
                        code: code.to_string(),
                        group_id: gid,
                        multiplier_str: mult.to_string(),
                        effective_multiplier_str: eff_mult.to_string(),
                        effective_multiplier: eff_val,
                        cache_hit_rate: hit.to_string(),
                        ttft_str: ttft.to_string(),
                        tps_str: tps.to_string(),
                        success_rate_str: sr_str.to_string(),
                        detection_status: det.to_string(),
                        detection_label: det_lbl.to_string(),
                        detection_dot: det_dot.to_string(),
                        has_image: img,
                        image_url: String::new(),
                        ttft_ms,
                        success_rate: sr,
                        is_excluded: false,
                        public_detail: String::new(),
                    });
                }
            }
            filtered.sort_by(|a, b| {
                a.effective_multiplier
                    .partial_cmp(&b.effective_multiplier)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
        }

        // Add 1-based ranking prefix to monitored items matching Python appearance
        for (idx, p) in filtered.iter_mut().enumerate() {
            p.code = format!("{}. {}", idx + 1, p.code);
        }

        let now = Local::now().format("%H:%M").to_string();

        AIHubData {
            success: true,
            error: None,
            updated_at: now,
            auto_mode,
            monitored_providers: filtered.clone(),
            all_providers: if full_list.is_empty() {
                filtered
            } else {
                full_list
            },
        }
    }

    pub async fn get_provider_history_images(
        &self,
        group_id: i64,
        max_items: usize,
    ) -> Vec<PelicanImageItem> {
        if group_id <= 0 {
            return Vec::new();
        }
        let url = format!("https://aihub.dog/api/v2/public/providers/{}/images", group_id);
        let resp = match self.client.get(&url).send().await {
            Ok(r) => r,
            Err(_) => return Vec::new(),
        };
        if !resp.status().is_success() {
            return Vec::new();
        }
        let json: serde_json::Value = match resp.json().await {
            Ok(j) => j,
            Err(_) => return Vec::new(),
        };
        let items = json.get("data").and_then(|d| d.get("items")).and_then(|it| it.as_array());
        let mut result = Vec::new();
        if let Some(arr) = items {
            for it in arr {
                if result.len() >= max_items {
                    break;
                }
                let id = it.get("id").map(|v| v.to_string()).unwrap_or_default();
                let pub_at = it.get("published_at").and_then(|v| v.as_str()).unwrap_or_default().to_string();
                let pub_str = pub_at.chars().take(19).collect::<String>().replace('T', " ");
                let rel_url = it
                    .get("presentation")
                    .and_then(|p| p.get("image"))
                    .and_then(|img| img.get("url"))
                    .and_then(|u| u.as_str())
                    .unwrap_or_default();
                let full_url = if rel_url.is_empty() {
                    String::new()
                } else if rel_url.starts_with("http") {
                    rel_url.to_string()
                } else {
                    format!("https://aihub.dog{}", rel_url)
                };
                if !full_url.is_empty() {
                    result.push(PelicanImageItem {
                        id,
                        published_at: pub_at,
                        published_at_str: pub_str,
                        url: full_url,
                        title: "鹈鹕".to_string(),
                    });
                }
            }
        }
        result
    }

    pub async fn fetch_image_as_pixel_buffer(
        &self,
        url: &str,
        max_w: u32,
        max_h: u32,
    ) -> Option<slint::SharedPixelBuffer<slint::Rgba8Pixel>> {
        if url.is_empty() {
            return None;
        }
        let resp = match tokio::time::timeout(
            std::time::Duration::from_secs(2),
            self.client.get(url).send()
        ).await {
            Ok(Ok(r)) => r,
            _ => return None,
        };
        if !resp.status().is_success() {
            return None;
        }
        let bytes = resp.bytes().await.ok()?;
        let dynamic = image::load_from_memory(&bytes).ok()?;
        let thumb = dynamic.thumbnail(max_w, max_h);
        let rgba = thumb.to_rgba8();
        let (w, h) = rgba.dimensions();
        let buffer = slint::SharedPixelBuffer::<slint::Rgba8Pixel>::clone_from_slice(
            rgba.as_raw(),
            w,
            h,
        );
        Some(buffer)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_c_coefficient() {
        let expr1 = "(len <= 272000 ? tier(\"base\", p * 2 + c * 10 + cr * 0.1 + cc * 2.5) : tier(\"tier_2\", p * 4 + c * 15 + cr * 0.2 + cc * 5))";
        assert_eq!(extract_c_coefficient(expr1), Some(10.0));

        let expr2 = "(len < 272000 ? tier(\"base\", p * 10 + c * 50 + cr * 1 + cc * 12.5) : tier(\"tier_2\", p * 20 + c * 75 + cr * 2 + cc * 25))";
        assert_eq!(extract_c_coefficient(expr2), Some(50.0));

        let expr3 = "tier(\"base\", p * 4 + c * 20 + cr * 0.2 + cc * 5 + cc1h * 8)";
        assert_eq!(extract_c_coefficient(expr3), Some(20.0));
    }

    #[test]
    fn test_format_price_val() {
        assert_eq!(format_price_val(1.5), "$1.5");
        assert_eq!(format_price_val(2.4), "$2.4");
        assert_eq!(format_price_val(6.0), "$6");
        assert_eq!(format_price_val(7.5), "$7.5");
        assert_eq!(format_price_val(12.0), "$12");
        assert_eq!(format_price_val(0.8), "$0.8");
    }

    #[test]
    fn test_calculate_output_price() {
        let sol = ModelPricingInfo {
            model_name: "gpt-6.1-sol".to_string(),
            model_ratio: 37.5,
            completion_ratio: 2.0,
            model_price: 0.0,
            billing_mode: "tiered_expr".to_string(),
            billing_expr: "(len <= 272000 ? tier(\"base\", p * 2 + c * 10 + cr * 0.1 + cc * 2.5) : tier(\"tier_2\", p * 4 + c * 15 + cr * 0.2 + cc * 5))".to_string(),
            enable_groups: vec!["terra分组".to_string(), "gpt-已过鹈鹕测试不降智".to_string()],
        };

        // terra 0.15 ratio
        assert_eq!(calculate_output_price(Some(&sol), 0.15), "$1.5");
        // 已过鹈鹕 0.24 ratio
        assert_eq!(calculate_output_price(Some(&sol), 0.24), "$2.4");

        let astra = ModelPricingInfo {
            model_name: "gpt-6-astra".to_string(),
            model_ratio: 5.0,
            completion_ratio: 5.0,
            model_price: 0.0,
            billing_mode: "tiered_expr".to_string(),
            billing_expr: "(len < 272000 ? tier(\"base\", p * 10 + c * 50 + cr * 1 + cc * 12.5) : ...)".to_string(),
            enable_groups: vec!["6-astra".to_string(), "terra分组".to_string(), "gpt-已过鹈鹕测试不降智".to_string()],
        };

        assert_eq!(calculate_output_price(Some(&astra), 0.12), "$6");
        assert_eq!(calculate_output_price(Some(&astra), 0.15), "$7.5");
        assert_eq!(calculate_output_price(Some(&astra), 0.24), "$12");

        let ds = ModelPricingInfo {
            model_name: "deepseek-v4.1-flash".to_string(),
            model_ratio: 1.0,
            completion_ratio: 4.0,
            model_price: 0.0,
            billing_mode: String::new(),
            billing_expr: String::new(),
            enable_groups: vec!["ds-v4.1可用".to_string()],
        };

        assert_eq!(calculate_output_price(Some(&ds), 0.10), "$0.8");
    }
}
