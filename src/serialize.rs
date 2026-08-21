//! JSON dumps/loads with a batch API so Python amortizes FFI cost.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList};
use serde_json::Value;

use crate::jsonutil::{parse_json_slice, py_to_value, read_buffer, value_to_py};

pub fn dumps_bytes(obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let value = py_to_value(obj)?;
    serde_json::to_vec(&value).map_err(|e| PyValueError::new_err(e.to_string()))
}

pub fn dumps_pretty_bytes(obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let value = py_to_value(obj)?;
    serde_json::to_vec_pretty(&value).map_err(|e| PyValueError::new_err(e.to_string()))
}

pub fn loads_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    let buf = read_buffer(obj)?;
    parse_json_slice(buf.as_slice()).map_err(PyValueError::new_err)
}

pub fn dumps_py<'py>(py: Python<'py>, obj: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyBytes>> {
    let bytes = dumps_bytes(obj)?;
    Ok(PyBytes::new(py, &bytes))
}

pub fn loads_py(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let value = loads_value(obj)?;
    value_to_py(py, &value)
}

pub fn dumps_batch_py<'py>(
    py: Python<'py>,
    objs: &Bound<'py, PyList>,
) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    for item in objs.iter() {
        let bytes = dumps_bytes(&item)?;
        out.append(PyBytes::new(py, &bytes))?;
    }
    Ok(out)
}

pub fn loads_batch_py(py: Python<'_>, payloads: &Bound<'_, PyList>) -> PyResult<Py<PyAny>> {
    let out = PyList::empty(py);
    for item in payloads.iter() {
        out.append(loads_py(py, &item)?)?;
    }
    Ok(out.into_any().unbind())
}
