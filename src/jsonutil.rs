//! Python ↔ JSON conversion used by the serializer and the validator.
//!
//! Bool is checked before int (Python `bool` is a subclass of `int`).
//! Datetime / UUID / Decimal / bytes are coerced to JSON-friendly forms.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyNone, PyString, PyTuple};
use serde_json::{Map, Number, Value};

pub fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.is_none() || obj.is_instance_of::<PyNone>() {
        return Ok(Value::Null);
    }
    if obj.is_instance_of::<PyBool>() {
        return Ok(Value::Bool(obj.extract::<bool>()?));
    }
    if obj.is_instance_of::<PyInt>() {
        if let Ok(i) = obj.extract::<i64>() {
            return Ok(Value::Number(i.into()));
        }
        if let Ok(u) = obj.extract::<u64>() {
            return Ok(Value::Number(u.into()));
        }
        let s: String = obj.str()?.extract()?;
        return Ok(Value::String(s));
    }
    if obj.is_instance_of::<PyFloat>() {
        let f: f64 = obj.extract()?;
        return match Number::from_f64(f) {
            Some(n) => Ok(Value::Number(n)),
            None => Ok(Value::Null),
        };
    }
    if obj.is_instance_of::<PyString>() {
        return Ok(Value::String(obj.extract::<String>()?));
    }
    if obj.is_instance_of::<PyBytes>() {
        let b = obj.downcast::<PyBytes>()?.as_bytes();
        if let Ok(s) = std::str::from_utf8(b) {
            return Ok(Value::String(s.to_string()));
        }
        let arr: Vec<Value> = b.iter().map(|x| Value::Number((*x).into())).collect();
        return Ok(Value::Array(arr));
    }
    if let Ok(list) = obj.downcast::<PyList>() {
        let mut arr = Vec::with_capacity(list.len());
        for item in list.iter() {
            arr.push(py_to_value(&item)?);
        }
        return Ok(Value::Array(arr));
    }
    if let Ok(tup) = obj.downcast::<PyTuple>() {
        let mut arr = Vec::with_capacity(tup.len());
        for item in tup.iter() {
            arr.push(py_to_value(&item)?);
        }
        return Ok(Value::Array(arr));
    }
    if let Ok(dict) = obj.downcast::<PyDict>() {
        let mut map = Map::with_capacity(dict.len());
        for (k, v) in dict.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_to_value(&v)?);
        }
        return Ok(Value::Object(map));
    }
    if obj.hasattr("model_dump")? {
        let dumped = obj.call_method0("model_dump")?;
        return py_to_value(&dumped);
    }
    if obj.hasattr("dict")? {
        let dumped = obj.call_method0("dict")?;
        if dumped.downcast::<PyDict>().is_ok() {
            return py_to_value(&dumped);
        }
    }
    if obj.hasattr("isoformat")? {
        let s: String = obj.call_method0("isoformat")?.extract()?;
        return Ok(Value::String(s));
    }
    let tn: String = obj.get_type().name()?.to_string();
    if tn == "UUID" || tn == "Decimal" || tn == "Path" || tn == "IPv4Address" || tn == "IPv6Address"
    {
        let s: String = obj.str()?.extract()?;
        return Ok(Value::String(s));
    }
    Err(PyTypeError::new_err(format!(
        "pyron: cannot serialize type '{tn}'"
    )))
}

pub fn value_to_py(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok(PyBool::new(py, *b).to_owned().into_any().unbind()),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_pyobject(py)?.into_any().unbind())
            } else if let Some(u) = n.as_u64() {
                Ok(u.into_pyobject(py)?.into_any().unbind())
            } else if let Some(f) = n.as_f64() {
                Ok(f.into_pyobject(py)?.into_any().unbind())
            } else {
                Ok(n.to_string().into_pyobject(py)?.into_any().unbind())
            }
        }
        Value::String(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(value_to_py(py, item)?)?;
            }
            Ok(list.into_any().unbind())
        }
        Value::Object(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(k, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
    }
}

/// Read UTF-8 bytes from `bytes`, `bytearray`, `memoryview`, or `str`.
/// `bytes` and `str` are borrowed (zero-copy). Everything else is copied.
pub fn read_buffer<'a>(obj: &'a Bound<'_, PyAny>) -> PyResult<CowBytes<'a>> {
    if let Ok(b) = obj.downcast::<PyBytes>() {
        return Ok(CowBytes::Borrowed(b.as_bytes()));
    }
    if let Ok(s) = obj.downcast::<PyString>() {
        return Ok(CowBytes::Borrowed(s.to_str()?.as_bytes()));
    }
    if let Ok(v) = obj.extract::<Vec<u8>>() {
        return Ok(CowBytes::Owned(v));
    }
    if let Ok(s) = obj.extract::<String>() {
        return Ok(CowBytes::Owned(s.into_bytes()));
    }
    Err(PyValueError::new_err(
        "expected bytes, bytearray, memoryview, or str",
    ))
}

pub enum CowBytes<'a> {
    Borrowed(&'a [u8]),
    Owned(Vec<u8>),
}

impl CowBytes<'_> {
    pub fn as_slice(&self) -> &[u8] {
        match self {
            CowBytes::Borrowed(s) => s,
            CowBytes::Owned(v) => v,
        }
    }
}

pub fn parse_json_slice(slice: &[u8]) -> Result<Value, String> {
    serde_json::from_slice(slice).map_err(|e| format!("invalid JSON: {e}"))
}
