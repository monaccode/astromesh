use pyo3::prelude::*;
use pyo3::types::PyDict;
use regex::Regex;
use std::sync::LazyLock;

static SENTENCE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?<=[.!?])\s+").unwrap());

// ---------------------------------------------------------------------------
// Helper: character-aware slicing
// ---------------------------------------------------------------------------

/// Return a substring by character offsets `[start..end)`.
fn char_slice(s: &str, start: usize, end: usize) -> &str {
    let mut indices = s.char_indices().map(|(i, _)| i).chain(std::iter::once(s.len()));
    let byte_start = indices.clone().nth(start).unwrap_or(s.len());
    let byte_end = indices.nth(end).unwrap_or(s.len());
    &s[byte_start..byte_end]
}

/// Character count (mirrors Python `len(str)`).
fn char_len(s: &str) -> usize {
    s.chars().count()
}

// ---------------------------------------------------------------------------
// Fixed chunker
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (document, metadata, chunk_size = 500, overlap = 50))]
pub fn rust_fixed_chunk<'py>(
    py: Python<'py>,
    document: &str,
    metadata: &Bound<'py, PyDict>,
    chunk_size: usize,
    overlap: usize,
) -> PyResult<Vec<Py<PyDict>>> {
    if document.is_empty() {
        return Ok(vec![]);
    }

    let doc_len = char_len(document);
    let mut chunks: Vec<Py<PyDict>> = Vec::new();
    let mut start: usize = 0;
    let mut i: usize = 0;

    while start < doc_len {
        let end = std::cmp::min(start + chunk_size, doc_len);
        let content = char_slice(document, start, end);

        let dict = PyDict::new(py);
        dict.set_item("content", content)?;

        let meta = metadata.copy()?;
        meta.set_item("chunk_index", i)?;
        meta.set_item("strategy", "fixed")?;
        dict.set_item("metadata", meta)?;

        chunks.push(dict.unbind());
        i += 1;

        start += chunk_size - overlap;
        if start >= doc_len {
            break;
        }
    }

    Ok(chunks)
}

// ---------------------------------------------------------------------------
// Recursive chunker
// ---------------------------------------------------------------------------

fn merge_parts(parts: &[String], chunk_size: usize) -> Vec<String> {
    let mut merged: Vec<String> = Vec::new();
    let mut current = String::new();

    for part in parts {
        if !current.is_empty() && char_len(&current) + char_len(part) > chunk_size {
            merged.push(current);
            current = part.clone();
        } else {
            current.push_str(part);
        }
    }
    if !current.is_empty() {
        merged.push(current);
    }
    merged
}

fn fixed_split(text: &str, chunk_size: usize, overlap: usize) -> Vec<String> {
    let text_len = char_len(text);
    let mut chunks: Vec<String> = Vec::new();
    let mut start: usize = 0;

    while start < text_len {
        let end = std::cmp::min(start + chunk_size, text_len);
        chunks.push(char_slice(text, start, end).to_string());
        start += chunk_size - overlap;
        if start >= text_len {
            break;
        }
    }
    chunks
}

fn split_recursive(
    text: &str,
    separators: &[String],
    chunk_size: usize,
    overlap: usize,
) -> Vec<String> {
    if char_len(text) <= chunk_size {
        return vec![text.to_string()];
    }

    for (sep_idx, sep) in separators.iter().enumerate() {
        let parts: Vec<&str> = text.split(sep.as_str()).collect();
        if parts.len() <= 1 {
            continue;
        }

        // Rebuild parts with separator appended (except possibly the last)
        let mut rebuilt: Vec<String> = Vec::new();
        for (idx, part) in parts.iter().enumerate() {
            if idx < parts.len() - 1 {
                rebuilt.push(format!("{}{}", part, sep));
            } else if !part.is_empty() {
                rebuilt.push(part.to_string());
            }
        }

        let merged = merge_parts(&rebuilt, chunk_size);

        if merged.iter().all(|m| char_len(m) <= chunk_size) {
            return merged;
        }

        let remaining_seps = &separators[sep_idx + 1..];
        let mut result: Vec<String> = Vec::new();
        for m in &merged {
            if char_len(m) <= chunk_size {
                result.push(m.clone());
            } else if !remaining_seps.is_empty() {
                result.extend(split_recursive(m, remaining_seps, chunk_size, overlap));
            } else {
                result.extend(fixed_split(m, chunk_size, overlap));
            }
        }
        return result;
    }

    fixed_split(text, chunk_size, overlap)
}

#[pyfunction]
#[pyo3(signature = (document, metadata, chunk_size = 500, overlap = 50, separators = None))]
pub fn rust_recursive_chunk<'py>(
    py: Python<'py>,
    document: &str,
    metadata: &Bound<'py, PyDict>,
    chunk_size: usize,
    overlap: usize,
    separators: Option<Vec<String>>,
) -> PyResult<Vec<Py<PyDict>>> {
    if document.is_empty() {
        return Ok(vec![]);
    }

    let seps = separators.unwrap_or_else(|| {
        vec![
            "\n\n".to_string(),
            "\n".to_string(),
            ". ".to_string(),
            " ".to_string(),
        ]
    });

    let pieces = split_recursive(document, &seps, chunk_size, overlap);
    let mut chunks: Vec<Py<PyDict>> = Vec::new();

    for (i, piece) in pieces.iter().enumerate() {
        let dict = PyDict::new(py);
        dict.set_item("content", piece.as_str())?;

        let meta = metadata.copy()?;
        meta.set_item("chunk_index", i)?;
        meta.set_item("strategy", "recursive")?;
        dict.set_item("metadata", meta)?;

        chunks.push(dict.unbind());
    }

    Ok(chunks)
}

// ---------------------------------------------------------------------------
// Sentence chunker
// ---------------------------------------------------------------------------

fn split_sentences(text: &str) -> Vec<String> {
    // Split on whitespace that follows [.!?], replicating
    // Python's `re.split(r"(?<=[.!?])\s+", text)`.
    let re = &*SENTENCE_RE;
    let parts: Vec<&str> = re.split(text).collect();
    let mut sentences: Vec<String> = Vec::new();

    for (idx, part) in parts.iter().enumerate() {
        if idx < parts.len() - 1 {
            sentences.push(format!("{} ", part));
        } else {
            sentences.push(part.to_string());
        }
    }
    sentences
}

#[pyfunction]
#[pyo3(signature = (document, metadata, chunk_size = 500, overlap = 0))]
pub fn rust_sentence_chunk<'py>(
    py: Python<'py>,
    document: &str,
    metadata: &Bound<'py, PyDict>,
    chunk_size: usize,
    _overlap: usize,
) -> PyResult<Vec<Py<PyDict>>> {
    if document.is_empty() {
        return Ok(vec![]);
    }

    let sentences = split_sentences(document);
    let mut chunks: Vec<Py<PyDict>> = Vec::new();
    let mut current = String::new();
    let mut i: usize = 0;

    for sentence in &sentences {
        if !current.is_empty() && char_len(&current) + char_len(sentence) > chunk_size {
            let trimmed = current.trim().to_string();
            let dict = PyDict::new(py);
            dict.set_item("content", &trimmed)?;

            let meta = metadata.copy()?;
            meta.set_item("chunk_index", i)?;
            meta.set_item("strategy", "sentence")?;
            dict.set_item("metadata", meta)?;

            chunks.push(dict.unbind());
            i += 1;
            current = sentence.clone();
        } else {
            current.push_str(sentence);
        }
    }

    let trimmed = current.trim().to_string();
    if !trimmed.is_empty() {
        let dict = PyDict::new(py);
        dict.set_item("content", &trimmed)?;

        let meta = metadata.copy()?;
        meta.set_item("chunk_index", i)?;
        meta.set_item("strategy", "sentence")?;
        dict.set_item("metadata", meta)?;

        chunks.push(dict.unbind());
    }

    Ok(chunks)
}

// ---------------------------------------------------------------------------
// Semantic helpers (cosine similarity + grouping)
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn rust_cosine_similarity(a: Vec<f64>, b: Vec<f64>) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }

    let dot: f64 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f64 = a.iter().map(|x| x * x).sum::<f64>().sqrt();
    let norm_b: f64 = b.iter().map(|x| x * x).sum::<f64>().sqrt();

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    dot / (norm_a * norm_b)
}

/// Group sentence indices by semantic similarity.
///
/// `similarities` contains the cosine similarity between consecutive sentences,
/// i.e. `similarities[i]` = similarity(sentence[i], sentence[i+1]).
/// Length must be `sentences.len() - 1`.
///
/// Returns a `Vec<Vec<usize>>` where each inner vec holds the indices of
/// sentences that belong to one group.
#[pyfunction]
pub fn rust_semantic_group(
    sentences: Vec<String>,
    similarities: Vec<f64>,
    threshold: f64,
    chunk_size: usize,
) -> Vec<Vec<usize>> {
    if sentences.is_empty() {
        return vec![];
    }

    let mut groups: Vec<Vec<usize>> = vec![vec![0]];

    for i in 1..sentences.len() {
        let sim = if i - 1 < similarities.len() {
            similarities[i - 1]
        } else {
            0.0
        };

        let current_group = groups.last().unwrap();
        let group_char_len: usize = current_group.iter().map(|&idx| char_len(&sentences[idx])).sum();

        if sim >= threshold && group_char_len + char_len(&sentences[i]) <= chunk_size {
            groups.last_mut().unwrap().push(i);
        } else {
            groups.push(vec![i]);
        }
    }

    groups
}
