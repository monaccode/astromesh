use pyo3::prelude::*;
use std::collections::HashMap;

#[pyclass]
pub struct RustCostIndex {
    // key: "agent:session", value: vec of (cost_usd, latency_ms, input_tokens, output_tokens, timestamp_secs)
    records: Vec<(String, String, String, String, f64, f64, i64, i64, f64)>,
    // agent, session, model, provider, cost, latency, input_tok, output_tok, timestamp
}

#[pymethods]
impl RustCostIndex {
    #[new]
    fn new() -> Self {
        Self { records: Vec::new() }
    }

    fn record(
        &mut self,
        agent_name: String,
        session_id: String,
        model: String,
        provider: String,
        cost_usd: f64,
        latency_ms: f64,
        input_tokens: i64,
        output_tokens: i64,
        timestamp: f64,
    ) {
        self.records.push((
            agent_name, session_id, model, provider,
            cost_usd, latency_ms, input_tokens, output_tokens, timestamp,
        ));
    }

    fn total_cost(
        &self,
        agent_name: Option<&str>,
        session_id: Option<&str>,
        since: Option<f64>,
    ) -> f64 {
        self.records
            .iter()
            .filter(|r| {
                agent_name.map_or(true, |a| r.0 == a)
                    && session_id.map_or(true, |s| r.1 == s)
                    && since.map_or(true, |t| r.8 >= t)
            })
            .map(|r| r.4)
            .sum()
    }

    fn group_by(&self, agent_name: Option<&str>, field: &str) -> HashMap<String, (f64, u32, i64)> {
        let mut groups: HashMap<String, (f64, u32, i64)> = HashMap::new();
        for r in &self.records {
            if let Some(a) = agent_name {
                if r.0 != a {
                    continue;
                }
            }
            let key = match field {
                "provider" => &r.3,
                "model" => &r.2,
                "session" => &r.1,
                _ => &r.3,
            };
            let entry = groups.entry(key.clone()).or_insert((0.0, 0, 0));
            entry.0 += r.4; // cost
            entry.1 += 1; // calls
            entry.2 += r.6 + r.7; // tokens
        }
        groups
    }
}
