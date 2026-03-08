use pyo3::prelude::*;

#[pyclass]
pub struct RustTokenBudget;

#[pymethods]
impl RustTokenBudget {
    #[new]
    fn new() -> Self { Self }

    /// Takes contents and token_counts as parallel vecs, plus budget.
    /// Returns indices of turns to keep (in original order).
    #[staticmethod]
    fn apply(contents: Vec<String>, token_counts: Vec<i64>, budget: i64) -> Vec<usize> {
        let n = contents.len();
        let mut selected: Vec<usize> = Vec::new();
        let mut used: i64 = 0;

        for i in (0..n).rev() {
            let cost = if token_counts[i] > 0 {
                token_counts[i]
            } else {
                contents[i].split_whitespace().count() as i64
            };
            if used + cost > budget {
                break;
            }
            selected.push(i);
            used += cost;
        }

        selected.reverse();
        selected
    }
}
