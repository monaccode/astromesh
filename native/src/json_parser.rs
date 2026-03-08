use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyList, PyNone, PyString};

/// Fast JSON parsing using serde_json, returning Python objects.
#[pyfunction]
pub fn rust_json_loads(py: Python<'_>, text: &str) -> PyResult<PyObject> {
    let value: serde_json::Value = serde_json::from_str(text)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("JSON parse error: {}", e)))?;
    json_to_py(py, &value)
}

fn json_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Null => Ok(PyNone::get(py).into_pyobject(py)?.into_any().unbind()),
        serde_json::Value::Bool(b) => Ok(PyBool::new(py, *b).into_pyobject(py)?.into_any().unbind()),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_pyobject(py)?.into_any().unbind())
            } else if let Some(f) = n.as_f64() {
                Ok(PyFloat::new(py, f).into_pyobject(py)?.into_any().unbind())
            } else {
                Ok(PyNone::get(py).into_pyobject(py)?.into_any().unbind())
            }
        }
        serde_json::Value::String(s) => Ok(PyString::new(py, s).into_pyobject(py)?.into_any().unbind()),
        serde_json::Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_to_py(py, item)?)?;
            }
            Ok(list.into_pyobject(py)?.into_any().unbind())
        }
        serde_json::Value::Object(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(k, json_to_py(py, v)?)?;
            }
            Ok(dict.into_pyobject(py)?.into_any().unbind())
        }
    }
}
