use pyo3::prelude::*;
use std::collections::HashMap;
use std::collections::VecDeque;
use std::time::{SystemTime, UNIX_EPOCH};

#[pyclass]
pub struct RustRateLimiter {
    calls: HashMap<String, VecDeque<f64>>,
}

#[pymethods]
impl RustRateLimiter {
    #[new]
    fn new() -> Self {
        Self { calls: HashMap::new() }
    }

    fn check(&mut self, tool_name: &str, window_seconds: f64, max_calls: u32) -> bool {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        let cutoff = now - window_seconds;

        let queue = self.calls.entry(tool_name.to_string()).or_default();

        // Remove expired entries from front (timestamps are ordered)
        while let Some(&front) = queue.front() {
            if front < cutoff {
                queue.pop_front();
            } else {
                break;
            }
        }

        if queue.len() >= max_calls as usize {
            return false;
        }

        queue.push_back(now);
        true
    }
}
