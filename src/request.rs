//! Query-string and header parsing for the request path.
//!
//! Handlers still receive a normal request object. Declared query and header
//! parameters are filled from this parse so that work does not stay in Python.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// `(query_dict, headers_dict)`.
///
/// Query values are form-decoded. The first value for a key wins.
/// Header names are lowercased. The first value for a name wins.
pub fn prepare_request<'py>(
    py: Python<'py>,
    query: &str,
    headers: &Bound<'py, PyList>,
) -> PyResult<Bound<'py, PyDict>> {
    let query_map = PyDict::new(py);
    if !query.is_empty() {
        for (key, value) in parse_query(query) {
            if !query_map.contains(&key)? {
                query_map.set_item(key, value)?;
            }
        }
    }
    let header_map = PyDict::new(py);
    for item in headers.iter() {
        let pair = item.downcast::<pyo3::types::PyTuple>()?;
        let name: String = pair.get_item(0)?.extract()?;
        let value: String = pair.get_item(1)?.extract()?;
        let name = name.to_ascii_lowercase();
        if !header_map.contains(&name)? {
            header_map.set_item(name, value)?;
        }
    }
    let out = PyDict::new(py);
    out.set_item("query", query_map)?;
    out.set_item("headers", header_map)?;
    Ok(out)
}

pub fn parse_query(query: &str) -> Vec<(String, String)> {
    let mut pairs = Vec::new();
    for part in query.split('&') {
        if part.is_empty() {
            continue;
        }
        let (raw_key, raw_value) = match part.split_once('=') {
            Some((key, value)) => (key, value),
            None => (part, ""),
        };
        pairs.push((form_decode(raw_key), form_decode(raw_value)));
    }
    pairs
}

fn form_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b'%' if i + 2 < bytes.len() => {
                let hex = &bytes[i + 1..i + 3];
                if let Ok(text) = std::str::from_utf8(hex) {
                    if let Ok(value) = u8::from_str_radix(text, 16) {
                        out.push(value);
                        i += 3;
                        continue;
                    }
                }
                out.push(b'%');
                i += 1;
            }
            byte => {
                out.push(byte);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

#[cfg(test)]
mod tests {
    use super::parse_query;

    #[test]
    fn decodes_plus_and_percent_and_keeps_first() {
        let pairs = parse_query("q=hello+world&q=second&raw=a%20b&flag");
        assert_eq!(
            pairs,
            vec![
                ("q".into(), "hello world".into()),
                ("q".into(), "second".into()),
                ("raw".into(), "a b".into()),
                ("flag".into(), "".into()),
            ]
        );
    }
}
