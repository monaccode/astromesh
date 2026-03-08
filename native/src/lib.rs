use pyo3::prelude::*;

mod chunking;
mod guardrails;
mod tokens;
mod ratelimit;
mod routing;
mod cost_tracker;
mod json_parser;

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Chunking
    m.add_function(wrap_pyfunction!(chunking::rust_fixed_chunk, m)?)?;
    m.add_function(wrap_pyfunction!(chunking::rust_recursive_chunk, m)?)?;
    m.add_function(wrap_pyfunction!(chunking::rust_sentence_chunk, m)?)?;
    m.add_function(wrap_pyfunction!(chunking::rust_cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(chunking::rust_semantic_group, m)?)?;
    // Guardrails
    m.add_class::<guardrails::RustPiiRedactor>()?;
    m.add_class::<guardrails::RustTopicFilter>()?;
    // Tokens
    m.add_class::<tokens::RustTokenBudget>()?;
    // Rate limiter
    m.add_class::<ratelimit::RustRateLimiter>()?;
    // Routing
    m.add_function(wrap_pyfunction!(routing::rust_ema_update, m)?)?;
    m.add_function(wrap_pyfunction!(routing::rust_rank_candidates, m)?)?;
    m.add_function(wrap_pyfunction!(routing::rust_detect_vision, m)?)?;
    // Cost tracker
    m.add_class::<cost_tracker::RustCostIndex>()?;
    // JSON parser
    m.add_function(wrap_pyfunction!(json_parser::rust_json_loads, m)?)?;
    Ok(())
}
