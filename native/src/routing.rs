use pyo3::prelude::*;
use pyo3::types::PyDict;

/// EMA update: current * alpha + observation * beta
#[pyfunction]
pub fn rust_ema_update(current: f64, observation: f64, alpha: f64, beta: f64) -> f64 {
    current * alpha + observation * beta
}

/// Detect if any message contains image_url content.
/// Messages are passed as list of dicts.
#[pyfunction]
pub fn rust_detect_vision(messages: Vec<Bound<'_, PyDict>>) -> PyResult<bool> {
    for msg in &messages {
        if let Some(content) = msg.get_item("content")? {
            // Check if content is a list
            if let Ok(list) = content.downcast::<pyo3::types::PyList>() {
                for item in list.iter() {
                    if let Ok(dict) = item.downcast::<PyDict>() {
                        if let Some(type_val) = dict.get_item("type")? {
                            if let Ok(type_str) = type_val.extract::<String>() {
                                if type_str == "image_url" {
                                    return Ok(true);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(false)
}

/// Rank candidates by strategy.
/// providers_data: list of tuples (name, estimated_cost, avg_latency_ms, is_circuit_open, circuit_open_until, supports_tools, supports_vision)
/// strategy: "cost_optimized", "latency_optimized", "round_robin", "capability_match"
/// For capability_match, additional kwargs needed -- keep it simple, just reorder.
#[pyfunction]
pub fn rust_rank_candidates(
    providers_data: Vec<(String, f64, f64, bool, f64, bool, bool)>,
    strategy: &str,
    request_count: u64,
    require_tools: bool,
    require_vision: bool,
) -> Vec<String> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs_f64();

    // Filter out circuit-broken providers
    let mut available: Vec<&(String, f64, f64, bool, f64, bool, bool)> = providers_data
        .iter()
        .filter(|p| {
            if p.3 { // is_circuit_open
                now >= p.4 // circuit_open_until
            } else {
                true
            }
        })
        .collect();

    match strategy {
        "cost_optimized" => {
            available.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
        }
        "latency_optimized" => {
            available.sort_by(|a, b| a.2.partial_cmp(&b.2).unwrap_or(std::cmp::Ordering::Equal));
        }
        "round_robin" => {
            if !available.is_empty() {
                let offset = (request_count as usize) % available.len();
                available.rotate_left(offset);
            }
        }
        "capability_match" => {
            available.retain(|p| {
                (!require_tools || p.5) && (!require_vision || p.6)
            });
        }
        _ => {}
    }

    available.iter().map(|p| p.0.clone()).collect()
}
