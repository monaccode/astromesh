use aho_corasick::AhoCorasick;
use pyo3::prelude::*;
use regex::Regex;

/// High-performance PII redaction using pre-compiled regex patterns.
///
/// Replaces email addresses, phone numbers, SSNs, and credit card numbers
/// with redaction placeholders in a single pass through the text.
#[pyclass]
pub struct RustPiiRedactor {
    email_re: Regex,
    phone_re: Regex,
    ssn_re: Regex,
    cc_re: Regex,
}

#[pymethods]
impl RustPiiRedactor {
    #[new]
    fn new() -> Self {
        Self {
            email_re: Regex::new(r"[\w.+-]+@[\w-]+\.[\w.-]+").unwrap(),
            phone_re: Regex::new(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b").unwrap(),
            ssn_re: Regex::new(r"\b\d{3}-\d{2}-\d{4}\b").unwrap(),
            cc_re: Regex::new(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b").unwrap(),
        }
    }

    /// Redact all PII patterns from the input text.
    ///
    /// Applies patterns in order: email, phone, SSN, credit card.
    /// Returns a new string with all matches replaced by redaction placeholders.
    fn redact(&self, text: &str) -> String {
        let text = self.email_re.replace_all(text, "[REDACTED_EMAIL]");
        let text = self.phone_re.replace_all(&text, "[REDACTED_PHONE]");
        let text = self.ssn_re.replace_all(&text, "[REDACTED_SSN]");
        let text = self.cc_re.replace_all(&text, "[REDACTED_CC]");
        text.into_owned()
    }
}

/// High-performance topic filter using Aho-Corasick automaton.
///
/// Performs a single O(n) pass over the text to detect any blocked topics,
/// compared to O(n*m) for naive per-topic scanning.
#[pyclass]
pub struct RustTopicFilter {
    automaton: AhoCorasick,
    topics: Vec<String>,
}

#[pymethods]
impl RustTopicFilter {
    #[new]
    fn new(topics: Vec<String>) -> Self {
        let automaton = AhoCorasick::builder()
            .ascii_case_insensitive(true)
            .build(&topics)
            .expect("Failed to build Aho-Corasick automaton");
        Self { automaton, topics }
    }

    /// Check if the text contains any blocked topic.
    ///
    /// Returns the first blocked topic found, or None if no match.
    fn contains_blocked(&self, text: &str) -> Option<String> {
        self.automaton
            .find(text)
            .map(|mat| self.topics[mat.pattern().as_usize()].clone())
    }
}
