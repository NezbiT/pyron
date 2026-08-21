//! Compiled JSON Schema subset — the validation hot path.
//!
//! Supports the constructs Pydantic v2 `model_json_schema()` actually emits:
//! `type`, `properties`, `required`, `additionalProperties`, `items`,
//! `minLength`/`maxLength`, `minimum`/`maximum`/`exclusive*`, `minItems`/
//! `maxItems`, `enum`, `const`, `anyOf`/`oneOf`, `$ref`/`$defs`, `format`
//! (email, uuid, date-time, date, uri, ipv4).

use std::collections::{HashMap, HashSet};

use serde_json::Value;

#[derive(Debug, Clone)]
pub enum Schema {
    Any,
    Null,
    Bool,
    Integer {
        minimum: Option<f64>,
        maximum: Option<f64>,
        exclusive_min: Option<f64>,
        exclusive_max: Option<f64>,
    },
    Number {
        minimum: Option<f64>,
        maximum: Option<f64>,
        exclusive_min: Option<f64>,
        exclusive_max: Option<f64>,
    },
    String {
        min_len: Option<usize>,
        max_len: Option<usize>,
        format: Option<StringFormat>,
        #[allow(dead_code)]
        pattern_contains: Option<String>,
    },
    Array {
        items: Option<Box<Schema>>,
        min_items: Option<usize>,
        max_items: Option<usize>,
    },
    Object {
        properties: HashMap<String, Schema>,
        required: Vec<String>,
        additional: Additional,
    },
    Enum(Vec<Value>),
    Const(Value),
    Union(Vec<Schema>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StringFormat {
    Email,
    Uuid,
    DateTime,
    Date,
    Uri,
    Ipv4,
}

#[derive(Debug, Clone)]
pub enum Additional {
    Allow,
    Forbid,
    Schema(Box<Schema>),
}

#[derive(Debug, Clone)]
pub struct ErrorItem {
    pub loc: Vec<String>,
    pub msg: String,
    pub kind: String,
}

impl ErrorItem {
    fn new(loc: &[String], msg: impl Into<String>, kind: impl Into<String>) -> Self {
        Self {
            loc: loc.to_vec(),
            msg: msg.into(),
            kind: kind.into(),
        }
    }
}

pub fn compile(schema: &Value) -> Result<Schema, String> {
    let defs = collect_defs(schema);
    compile_with_defs(schema, &defs)
}

fn collect_defs(schema: &Value) -> HashMap<String, Value> {
    let mut defs = HashMap::new();
    if let Some(obj) = schema.as_object() {
        for key in ["$defs", "definitions"] {
            if let Some(Value::Object(map)) = obj.get(key) {
                for (k, v) in map {
                    defs.insert(k.clone(), v.clone());
                }
            }
        }
    }
    defs
}

fn compile_with_defs(schema: &Value, defs: &HashMap<String, Value>) -> Result<Schema, String> {
    if let Some(r) = schema.get("$ref").and_then(|v| v.as_str()) {
        let name = r.rsplit('/').next().unwrap_or(r);
        let resolved = defs
            .get(name)
            .ok_or_else(|| format!("unresolved $ref: {r}"))?;
        return compile_with_defs(resolved, defs);
    }
    if schema.get("const").is_some() {
        return Ok(Schema::Const(schema.get("const").unwrap().clone()));
    }
    if let Some(Value::Array(opts)) = schema.get("enum") {
        return Ok(Schema::Enum(opts.clone()));
    }
    if let Some(Value::Array(opts)) = schema.get("anyOf").or_else(|| schema.get("oneOf")) {
        let mut parts = Vec::with_capacity(opts.len());
        for o in opts {
            parts.push(compile_with_defs(o, defs)?);
        }
        return Ok(Schema::Union(parts));
    }
    let ty = schema
        .get("type")
        .and_then(|v| {
            if let Some(s) = v.as_str() {
                Some(vec![s.to_string()])
            } else if let Some(arr) = v.as_array() {
                Some(
                    arr.iter()
                        .filter_map(|x| x.as_str().map(|s| s.to_string()))
                        .collect(),
                )
            } else {
                None
            }
        })
        .unwrap_or_default();

    if ty.len() > 1 {
        let mut parts = Vec::new();
        for t in &ty {
            let mut clone = schema.clone();
            if let Some(obj) = clone.as_object_mut() {
                obj.insert("type".into(), Value::String(t.clone()));
            }
            parts.push(compile_with_defs(&clone, defs)?);
        }
        return Ok(Schema::Union(parts));
    }

    match ty.first().map(|s| s.as_str()).unwrap_or("") {
        "" | "any" => {
            if schema.get("properties").is_some() {
                compile_object(schema, defs)
            } else {
                Ok(Schema::Any)
            }
        }
        "null" => Ok(Schema::Null),
        "boolean" => Ok(Schema::Bool),
        "integer" => Ok(Schema::Integer {
            minimum: num_opt(schema, "minimum"),
            maximum: num_opt(schema, "maximum"),
            exclusive_min: num_opt(schema, "exclusiveMinimum"),
            exclusive_max: num_opt(schema, "exclusiveMaximum"),
        }),
        "number" => Ok(Schema::Number {
            minimum: num_opt(schema, "minimum"),
            maximum: num_opt(schema, "maximum"),
            exclusive_min: num_opt(schema, "exclusiveMinimum"),
            exclusive_max: num_opt(schema, "exclusiveMaximum"),
        }),
        "string" => Ok(Schema::String {
            min_len: usize_opt(schema, "minLength"),
            max_len: usize_opt(schema, "maxLength"),
            format: schema
                .get("format")
                .and_then(|v| v.as_str())
                .and_then(parse_format),
            pattern_contains: None,
        }),
        "array" => {
            let items = match schema.get("items") {
                Some(i) => Some(Box::new(compile_with_defs(i, defs)?)),
                None => None,
            };
            Ok(Schema::Array {
                items,
                min_items: usize_opt(schema, "minItems"),
                max_items: usize_opt(schema, "maxItems"),
            })
        }
        "object" => compile_object(schema, defs),
        other => Err(format!("unsupported schema type: {other}")),
    }
}

fn compile_object(schema: &Value, defs: &HashMap<String, Value>) -> Result<Schema, String> {
    let mut properties = HashMap::new();
    if let Some(Value::Object(props)) = schema.get("properties") {
        for (k, v) in props {
            properties.insert(k.clone(), compile_with_defs(v, defs)?);
        }
    }
    let required = schema
        .get("required")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    let additional = match schema.get("additionalProperties") {
        Some(Value::Bool(false)) => Additional::Forbid,
        Some(Value::Bool(true)) | None => Additional::Allow,
        Some(other) => Additional::Schema(Box::new(compile_with_defs(other, defs)?)),
    };
    Ok(Schema::Object {
        properties,
        required,
        additional,
    })
}

fn num_opt(schema: &Value, key: &str) -> Option<f64> {
    schema.get(key).and_then(|v| v.as_f64().or_else(|| v.as_i64().map(|i| i as f64)))
}

fn usize_opt(schema: &Value, key: &str) -> Option<usize> {
    schema.get(key).and_then(|v| v.as_u64()).map(|n| n as usize)
}

fn parse_format(fmt: &str) -> Option<StringFormat> {
    match fmt {
        "email" => Some(StringFormat::Email),
        "uuid" | "uuid4" => Some(StringFormat::Uuid),
        "date-time" | "datetime" => Some(StringFormat::DateTime),
        "date" => Some(StringFormat::Date),
        "uri" | "url" => Some(StringFormat::Uri),
        "ipv4" => Some(StringFormat::Ipv4),
        _ => None,
    }
}

pub fn validate(schema: &Schema, value: &Value, fail_fast: bool) -> Vec<ErrorItem> {
    let mut errors = Vec::new();
    let mut loc = Vec::new();
    walk(schema, value, &mut loc, &mut errors, fail_fast);
    errors
}

fn walk(
    schema: &Schema,
    value: &Value,
    loc: &mut Vec<String>,
    errors: &mut Vec<ErrorItem>,
    fail_fast: bool,
) {
    if fail_fast && !errors.is_empty() {
        return;
    }
    match schema {
        Schema::Any => {}
        Schema::Null => {
            if !value.is_null() {
                errors.push(ErrorItem::new(loc, "must be null", "none_required"));
            }
        }
        Schema::Bool => {
            if !value.is_boolean() {
                errors.push(ErrorItem::new(loc, "must be a boolean", "bool_type"));
            }
        }
        Schema::Integer {
            minimum,
            maximum,
            exclusive_min,
            exclusive_max,
        } => match value {
            Value::Number(n) if n.is_i64() || n.is_u64() || n.as_f64().is_some_and(|f| f.fract() == 0.0) => {
                let f = n.as_f64().unwrap_or(0.0);
                check_bounds(f, *minimum, *maximum, *exclusive_min, *exclusive_max, loc, errors);
            }
            _ => errors.push(ErrorItem::new(loc, "must be an integer", "int_type")),
        },
        Schema::Number {
            minimum,
            maximum,
            exclusive_min,
            exclusive_max,
        } => match value {
            Value::Number(n) => {
                if let Some(f) = n.as_f64() {
                    check_bounds(f, *minimum, *maximum, *exclusive_min, *exclusive_max, loc, errors);
                }
            }
            _ => errors.push(ErrorItem::new(loc, "must be a number", "float_type")),
        },
        Schema::String {
            min_len,
            max_len,
            format,
            ..
        } => match value {
            Value::String(s) => {
                let chars = s.chars().count();
                if let Some(min) = min_len {
                    if chars < *min {
                        errors.push(ErrorItem::new(
                            loc,
                            format!("must be at least {min} characters"),
                            "string_too_short",
                        ));
                    }
                }
                if let Some(max) = max_len {
                    if chars > *max {
                        errors.push(ErrorItem::new(
                            loc,
                            format!("must be at most {max} characters"),
                            "string_too_long",
                        ));
                    }
                }
                if let Some(fmt) = format {
                    if let Some(msg) = check_format(s, *fmt) {
                        errors.push(ErrorItem::new(loc, msg, "string_pattern"));
                    }
                }
            }
            _ => errors.push(ErrorItem::new(loc, "must be a string", "string_type")),
        },
        Schema::Array {
            items,
            min_items,
            max_items,
        } => match value {
            Value::Array(arr) => {
                if let Some(min) = min_items {
                    if arr.len() < *min {
                        errors.push(ErrorItem::new(
                            loc,
                            format!("must have at least {min} items"),
                            "too_short",
                        ));
                    }
                }
                if let Some(max) = max_items {
                    if arr.len() > *max {
                        errors.push(ErrorItem::new(
                            loc,
                            format!("must have at most {max} items"),
                            "too_long",
                        ));
                    }
                }
                if let Some(item_schema) = items {
                    for (i, item) in arr.iter().enumerate() {
                        loc.push(i.to_string());
                        walk(item_schema, item, loc, errors, fail_fast);
                        loc.pop();
                        if fail_fast && !errors.is_empty() {
                            return;
                        }
                    }
                }
            }
            _ => errors.push(ErrorItem::new(loc, "must be an array", "list_type")),
        },
        Schema::Object {
            properties,
            required,
            additional,
        } => match value {
            Value::Object(map) => {
                for key in required {
                    if !map.contains_key(key) {
                        loc.push(key.clone());
                        errors.push(ErrorItem::new(loc, "field required", "missing"));
                        loc.pop();
                        if fail_fast {
                            return;
                        }
                    }
                }
                let mut seen: HashSet<&str> = HashSet::new();
                for (k, v) in map {
                    loc.push(k.clone());
                    if let Some(sub) = properties.get(k) {
                        walk(sub, v, loc, errors, fail_fast);
                        seen.insert(k.as_str());
                    } else {
                        match additional {
                            Additional::Allow => {}
                            Additional::Forbid => {
                                errors.push(ErrorItem::new(
                                    loc,
                                    "extra field not permitted",
                                    "extra_forbidden",
                                ));
                            }
                            Additional::Schema(s) => walk(s, v, loc, errors, fail_fast),
                        }
                    }
                    loc.pop();
                    if fail_fast && !errors.is_empty() {
                        return;
                    }
                }
                let _ = seen;
            }
            _ => errors.push(ErrorItem::new(loc, "must be an object", "dict_type")),
        },
        Schema::Enum(opts) => {
            if !opts.iter().any(|o| json_eq(o, value)) {
                errors.push(ErrorItem::new(loc, "value is not a permitted choice", "enum"));
            }
        }
        Schema::Const(c) => {
            if !json_eq(c, value) {
                errors.push(ErrorItem::new(loc, "value does not match const", "const"));
            }
        }
        Schema::Union(parts) => {
            let mut matched = false;
            for p in parts {
                let mut inner = Vec::new();
                walk(p, value, loc, &mut inner, true);
                if inner.is_empty() {
                    matched = true;
                    break;
                }
            }
            if !matched {
                errors.push(ErrorItem::new(
                    loc,
                    "value does not match any allowed type",
                    "union_tag_invalid",
                ));
            }
        }
    }
}

fn check_bounds(
    f: f64,
    minimum: Option<f64>,
    maximum: Option<f64>,
    exclusive_min: Option<f64>,
    exclusive_max: Option<f64>,
    loc: &[String],
    errors: &mut Vec<ErrorItem>,
) {
    if let Some(min) = minimum {
        if f < min {
            errors.push(ErrorItem::new(
                loc,
                format!("must be greater than or equal to {min}"),
                "greater_than_equal",
            ));
        }
    }
    if let Some(max) = maximum {
        if f > max {
            errors.push(ErrorItem::new(
                loc,
                format!("must be less than or equal to {max}"),
                "less_than_equal",
            ));
        }
    }
    if let Some(min) = exclusive_min {
        if f <= min {
            errors.push(ErrorItem::new(
                loc,
                format!("must be greater than {min}"),
                "greater_than",
            ));
        }
    }
    if let Some(max) = exclusive_max {
        if f >= max {
            errors.push(ErrorItem::new(
                loc,
                format!("must be less than {max}"),
                "less_than",
            ));
        }
    }
}

fn check_format(s: &str, fmt: StringFormat) -> Option<String> {
    match fmt {
        StringFormat::Email => {
            if !(s.contains('@') && s.contains('.') && s.len() >= 5 && !s.starts_with('@')) {
                Some("must be a valid email address".into())
            } else {
                None
            }
        }
        StringFormat::Uuid => {
            if !is_uuid(s) {
                Some("must be a UUID".into())
            } else {
                None
            }
        }
        StringFormat::Date => {
            if !is_date(s) {
                Some("must be a date (YYYY-MM-DD)".into())
            } else {
                None
            }
        }
        StringFormat::DateTime => {
            if !(s.len() >= 19 && s.as_bytes().get(10) == Some(&b'T')) {
                Some("must be an ISO 8601 date-time".into())
            } else {
                None
            }
        }
        StringFormat::Uri => {
            if !(s.starts_with("http://") || s.starts_with("https://") || s.starts_with("mailto:"))
            {
                Some("must be a URI".into())
            } else {
                None
            }
        }
        StringFormat::Ipv4 => {
            if !is_ipv4(s) {
                Some("must be an IPv4 address".into())
            } else {
                None
            }
        }
    }
}

fn is_uuid(s: &str) -> bool {
    let b = s.as_bytes();
    if b.len() != 36 {
        return false;
    }
    for (i, c) in b.iter().enumerate() {
        if i == 8 || i == 13 || i == 18 || i == 23 {
            if *c != b'-' {
                return false;
            }
        } else if !c.is_ascii_hexdigit() {
            return false;
        }
    }
    true
}

fn is_date(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 10
        && b[4] == b'-'
        && b[7] == b'-'
        && b[0..4].iter().all(|c| c.is_ascii_digit())
        && b[5..7].iter().all(|c| c.is_ascii_digit())
        && b[8..10].iter().all(|c| c.is_ascii_digit())
}

fn is_ipv4(s: &str) -> bool {
    let mut n = 0;
    for part in s.split('.') {
        n += 1;
        if n > 4 {
            return false;
        }
        if part.is_empty() || part.len() > 3 {
            return false;
        }
        if part.len() > 1 && part.starts_with('0') {
            return false;
        }
        match part.parse::<u8>() {
            Ok(_) => {}
            Err(_) => return false,
        }
    }
    n == 4
}

fn json_eq(a: &Value, b: &Value) -> bool {
    a == b
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn object_required_and_bounds() {
        let schema = compile(&json!({
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "price": {"type": "number", "minimum": 0}
            },
            "required": ["title", "price"],
            "additionalProperties": false
        }))
        .unwrap();
        assert!(validate(&schema, &json!({"title": "A", "price": 9.5}), true).is_empty());
        assert!(!validate(&schema, &json!({"title": "A"}), true).is_empty());
        assert!(!validate(&schema, &json!({"title": "A", "price": -1}), true).is_empty());
        assert!(!validate(&schema, &json!({"title": "A", "price": 1, "x": 1}), true).is_empty());
    }

    #[test]
    fn any_of_optional() {
        let schema = compile(&json!({
            "anyOf": [{"type": "string"}, {"type": "null"}]
        }))
        .unwrap();
        assert!(validate(&schema, &json!("hi"), true).is_empty());
        assert!(validate(&schema, &json!(null), true).is_empty());
        assert!(!validate(&schema, &json!(3), true).is_empty());
    }

    #[test]
    fn email_format() {
        let schema = compile(&json!({"type": "string", "format": "email"})).unwrap();
        assert!(validate(&schema, &json!("ada@ex.com"), true).is_empty());
        assert!(!validate(&schema, &json!("nope"), true).is_empty());
    }
}
