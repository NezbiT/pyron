//! Pyron Rust core, exposed to Python as `pyron._core` via PyO3.
//!
//! FFI rules used throughout:
//! - Borrow `bytes` / `str` (buffer protocol) — no extra copy on the way in.
//! - Batch methods (`find_batch`, `validate_batch`, `dumps_batch`) so a
//!   request fan-out pays the GIL/FFI tax once.
//! - Release the GIL around CPU-bound JSON parse + validate.

mod jsonutil;
mod method;
mod openapi;
mod request;
mod router;
mod serialize;
mod validator;

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyList, PyModule, PyTuple};
use serde_json::Value;

use crate::jsonutil::{parse_json_slice, py_to_value, read_buffer, value_to_py};
use crate::method::Method;
use crate::openapi::OpenApiInner;
use crate::router::{FindResult, RouterInner};
use crate::validator::Schema;

const VERSION: &str = env!("CARGO_PKG_VERSION");

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

#[pyclass(module = "pyron._core", name = "Router")]
pub struct PyRouter {
    inner: RouterInner,
}

#[pymethods]
impl PyRouter {
    #[new]
    fn new() -> Self {
        Self {
            inner: RouterInner::new(),
        }
    }

    /// Register `method path → route_id`. Raises ValueError on collision.
    fn add(&mut self, method: &str, path: &str, route_id: u32) -> PyResult<()> {
        let m = Method::parse(method)
            .ok_or_else(|| PyValueError::new_err(format!("unknown HTTP method: {method}")))?;
        self.inner
            .add(m, path, route_id)
            .map_err(PyValueError::new_err)
    }

    /// `(route_id, params_dict)` on hit; `(None, allowed_methods)` on 405;
    /// `None` on 404.
    fn find(&self, py: Python<'_>, method: &str, path: &str) -> PyResult<Py<PyAny>> {
        let m = match Method::parse(method) {
            Some(m) => m,
            None => return Ok(py.None()),
        };
        match self.inner.find(m, path) {
            FindResult::Found(hit) => {
                let params = PyDict::new(py);
                for (k, v) in hit.params {
                    params.set_item(k, v)?;
                }
                let tup = PyTuple::new(py, [hit.route_id.into_pyobject(py)?.into_any(), params.into_any()])?;
                Ok(tup.into_any().unbind())
            }
            FindResult::MethodNotAllowed { allowed } => {
                let list = PyList::new(py, allowed)?;
                let tup = PyTuple::new(py, [py.None().into_bound(py), list.into_any()])?;
                Ok(tup.into_any().unbind())
            }
            FindResult::NotFound => Ok(py.None()),
        }
    }

    /// Batch lookup. Each item is `(method, path)`.
    fn find_batch(&self, py: Python<'_>, items: Bound<'_, PyList>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for item in items.iter() {
            let pair = item.downcast::<PyTuple>()?;
            let method: String = pair.get_item(0)?.extract()?;
            let path: String = pair.get_item(1)?.extract()?;
            out.append(self.find(py, &method, &path)?)?;
        }
        Ok(out.into_any().unbind())
    }

    fn __len__(&self) -> usize {
        self.inner.len() as usize
    }
}

// ---------------------------------------------------------------------------
// Schema registry + validator
// ---------------------------------------------------------------------------

#[pyclass(module = "pyron._core", name = "SchemaRegistry")]
pub struct PySchemaRegistry {
    schemas: HashMap<u32, Schema>,
    next_id: u32,
}

#[pymethods]
impl PySchemaRegistry {
    #[new]
    fn new() -> Self {
        Self {
            schemas: HashMap::new(),
            next_id: 1,
        }
    }

    /// Compile a JSON Schema document (object or JSON string) and return an id.
    fn register(&mut self, schema: Bound<'_, PyAny>) -> PyResult<u32> {
        let value = coerce_schema(&schema)?;
        let compiled = validator::compile(&value).map_err(PyValueError::new_err)?;
        let id = self.next_id;
        self.next_id += 1;
        self.schemas.insert(id, compiled);
        Ok(id)
    }

    /// Validate `data` (bytes / str / Python object) against `schema_id`.
    ///
    /// Returns `(True, parsed_value)` or `(False, [{"loc", "msg", "type"}])`.
    #[pyo3(signature = (schema_id, data, fail_fast=true))]
    fn validate(
        &self,
        py: Python<'_>,
        schema_id: u32,
        data: Bound<'_, PyAny>,
        fail_fast: bool,
    ) -> PyResult<Py<PyAny>> {
        let schema = self
            .schemas
            .get(&schema_id)
            .ok_or_else(|| PyValueError::new_err(format!("unknown schema id {schema_id}")))?;
        let value = coerce_data(&data)?;
        let errors = py.allow_threads(|| validator::validate(schema, &value, fail_fast));
        pack_result(py, &value, errors)
    }

    /// One FFI call, many payloads. Each payload is bytes/str/object.
    #[pyo3(signature = (schema_id, payloads, fail_fast=true))]
    fn validate_batch(
        &self,
        py: Python<'_>,
        schema_id: u32,
        payloads: Bound<'_, PyList>,
        fail_fast: bool,
    ) -> PyResult<Py<PyAny>> {
        let schema = self
            .schemas
            .get(&schema_id)
            .ok_or_else(|| PyValueError::new_err(format!("unknown schema id {schema_id}")))?;
        let mut values: Vec<Value> = Vec::with_capacity(payloads.len());
        for item in payloads.iter() {
            values.push(coerce_data(&item)?);
        }
        let results: Vec<Vec<validator::ErrorItem>> = py.allow_threads(|| {
            values
                .iter()
                .map(|v| validator::validate(schema, v, fail_fast))
                .collect()
        });
        let out = PyList::empty(py);
        for (value, errors) in values.iter().zip(results.into_iter()) {
            out.append(pack_result(py, value, errors)?)?;
        }
        Ok(out.into_any().unbind())
    }

    fn __len__(&self) -> usize {
        self.schemas.len()
    }
}

fn coerce_schema(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.downcast::<pyo3::types::PyDict>().is_ok() {
        return py_to_value(obj);
    }
    let buf = read_buffer(obj)?;
    parse_json_slice(buf.as_slice()).map_err(PyValueError::new_err)
}

fn coerce_data(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.downcast::<pyo3::types::PyBytes>().is_ok()
        || obj.downcast::<pyo3::types::PyString>().is_ok()
    {
        let buf = read_buffer(obj)?;
        return parse_json_slice(buf.as_slice()).map_err(PyValueError::new_err);
    }
    if let Ok(v) = obj.extract::<Vec<u8>>() {
        return parse_json_slice(&v).map_err(PyValueError::new_err);
    }
    py_to_value(obj)
}

fn pack_result(
    py: Python<'_>,
    value: &Value,
    errors: Vec<validator::ErrorItem>,
) -> PyResult<Py<PyAny>> {
    if errors.is_empty() {
        let parsed = value_to_py(py, value)?;
        let tup = PyTuple::new(
            py,
            [
                PyBool::new(py, true).to_owned().into_any(),
                parsed.into_bound(py),
            ],
        )?;
        Ok(tup.into_any().unbind())
    } else {
        let list = PyList::empty(py);
        for e in errors {
            let d = PyDict::new(py);
            d.set_item("loc", e.loc)?;
            d.set_item("msg", e.msg)?;
            d.set_item("type", e.kind)?;
            list.append(d)?;
        }
        let tup = PyTuple::new(
            py,
            [
                PyBool::new(py, false).to_owned().into_any(),
                list.into_any(),
            ],
        )?;
        Ok(tup.into_any().unbind())
    }
}

// ---------------------------------------------------------------------------
// OpenAPI builder
// ---------------------------------------------------------------------------

#[pyclass(module = "pyron._core", name = "OpenApiBuilder")]
pub struct PyOpenApiBuilder {
    inner: OpenApiInner,
}

#[pymethods]
impl PyOpenApiBuilder {
    #[new]
    #[pyo3(signature = (title, version, description=None))]
    fn new(title: String, version: String, description: Option<String>) -> Self {
        Self {
            inner: OpenApiInner::new(title, version, description),
        }
    }

    fn add_schema(&mut self, name: String, schema: Bound<'_, PyAny>) -> PyResult<()> {
        self.inner.add_schema(name, coerce_schema(&schema)?);
        Ok(())
    }

    #[pyo3(signature = (url, description=None))]
    fn add_server(&mut self, url: String, description: Option<String>) {
        self.inner.add_server(url, description);
    }

    #[pyo3(signature = (name, description=None))]
    fn add_tag(&mut self, name: String, description: Option<String>) {
        self.inner.add_tag(name, description);
    }

    /// `operation` is a JSON object (dict or JSON string).
    fn add_operation(
        &mut self,
        method: &str,
        path: &str,
        operation: Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let op = coerce_schema(&operation)?;
        self.inner
            .add_operation(method, path, op)
            .map_err(PyValueError::new_err)
    }

    #[pyo3(signature = (pretty=false))]
    fn build(&self, pretty: bool) -> PyResult<String> {
        self.inner
            .build_string(pretty)
            .map_err(PyValueError::new_err)
    }

    fn as_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        value_to_py(py, &self.inner.build())
    }
}

// ---------------------------------------------------------------------------
// Module-level serialize helpers
// ---------------------------------------------------------------------------

#[pyfunction]
fn dumps(py: Python<'_>, obj: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(serialize::dumps_py(py, &obj)?.into_any().unbind())
}

#[pyfunction]
fn dumps_str(obj: Bound<'_, PyAny>) -> PyResult<String> {
    let bytes = serialize::dumps_bytes(&obj)?;
    String::from_utf8(bytes).map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn dumps_pretty(obj: Bound<'_, PyAny>) -> PyResult<String> {
    let bytes = serialize::dumps_pretty_bytes(&obj)?;
    String::from_utf8(bytes).map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn loads(py: Python<'_>, data: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    serialize::loads_py(py, &data)
}

#[pyfunction]
fn dumps_batch(py: Python<'_>, objs: Bound<'_, PyList>) -> PyResult<Py<PyAny>> {
    Ok(serialize::dumps_batch_py(py, &objs)?.into_any().unbind())
}

#[pyfunction]
fn loads_batch(py: Python<'_>, payloads: Bound<'_, PyList>) -> PyResult<Py<PyAny>> {
    serialize::loads_batch_py(py, &payloads)
}

#[pyfunction]
fn core_kind() -> &'static str {
    "rust"
}

#[pyfunction]
fn prepare_request<'py>(
    py: Python<'py>,
    query: &str,
    headers: &Bound<'py, PyList>,
) -> PyResult<Bound<'py, PyDict>> {
    request::prepare_request(py, query, headers)
}

// ---------------------------------------------------------------------------
// pymodule
// ---------------------------------------------------------------------------

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", VERSION)?;
    m.add("CORE", "rust")?;
    m.add_class::<PyRouter>()?;
    m.add_class::<PySchemaRegistry>()?;
    m.add_class::<PyOpenApiBuilder>()?;
    m.add_function(wrap_pyfunction!(dumps, m)?)?;
    m.add_function(wrap_pyfunction!(dumps_str, m)?)?;
    m.add_function(wrap_pyfunction!(dumps_pretty, m)?)?;
    m.add_function(wrap_pyfunction!(loads, m)?)?;
    m.add_function(wrap_pyfunction!(dumps_batch, m)?)?;
    m.add_function(wrap_pyfunction!(loads_batch, m)?)?;
    m.add_function(wrap_pyfunction!(core_kind, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_request, m)?)?;
    Ok(())
}
