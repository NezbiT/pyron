//! Assemble an OpenAPI 3.1 document from registered operations and schemas.
//! Path insertion order is preserved via IndexMap.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Info {
    pub title: String,
    pub version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct OpenApiInner {
    pub info: Info,
    pub servers: Vec<Value>,
    pub paths: IndexMap<String, IndexMap<String, Value>>,
    pub schemas: IndexMap<String, Value>,
    pub tags: Vec<Value>,
}

impl Default for Info {
    fn default() -> Self {
        Self {
            title: "Pyron".into(),
            version: "0.1.0".into(),
            description: None,
        }
    }
}

impl OpenApiInner {
    pub fn new(title: String, version: String, description: Option<String>) -> Self {
        Self {
            info: Info {
                title,
                version,
                description,
            },
            ..Default::default()
        }
    }

    pub fn add_schema(&mut self, name: String, schema: Value) {
        self.schemas.insert(name, schema);
    }

    pub fn add_server(&mut self, url: String, description: Option<String>) {
        let mut obj = serde_json::Map::new();
        obj.insert("url".into(), Value::String(url));
        if let Some(d) = description {
            obj.insert("description".into(), Value::String(d));
        }
        self.servers.push(Value::Object(obj));
    }

    pub fn add_tag(&mut self, name: String, description: Option<String>) {
        let mut obj = serde_json::Map::new();
        obj.insert("name".into(), Value::String(name));
        if let Some(d) = description {
            obj.insert("description".into(), Value::String(d));
        }
        self.tags.push(Value::Object(obj));
    }

    pub fn add_operation(
        &mut self,
        method: &str,
        path: &str,
        operation: Value,
    ) -> Result<(), String> {
        let m = method.to_ascii_lowercase();
        let allowed = [
            "get", "post", "put", "patch", "delete", "head", "options", "trace",
        ];
        if !allowed.contains(&m.as_str()) {
            return Err(format!("unknown HTTP method for OpenAPI: {method}"));
        }
        self.paths
            .entry(path.to_string())
            .or_default()
            .insert(m, operation);
        Ok(())
    }

    pub fn build(&self) -> Value {
        let mut paths = serde_json::Map::new();
        for (path, ops) in &self.paths {
            let mut opmap = serde_json::Map::new();
            for (method, op) in ops {
                opmap.insert(method.clone(), op.clone());
            }
            paths.insert(path.clone(), Value::Object(opmap));
        }
        let mut components = serde_json::Map::new();
        if !self.schemas.is_empty() {
            let mut schemas = serde_json::Map::new();
            for (k, v) in &self.schemas {
                schemas.insert(k.clone(), v.clone());
            }
            components.insert("schemas".into(), Value::Object(schemas));
        }
        let mut doc = json!({
            "openapi": "3.1.0",
            "info": {
                "title": self.info.title,
                "version": self.info.version,
            },
            "paths": paths,
        });
        if let Some(desc) = &self.info.description {
            doc["info"]["description"] = Value::String(desc.clone());
        }
        if !self.servers.is_empty() {
            doc["servers"] = Value::Array(self.servers.clone());
        }
        if !self.tags.is_empty() {
            doc["tags"] = Value::Array(self.tags.clone());
        }
        if !components.is_empty() {
            doc["components"] = Value::Object(components);
        }
        doc
    }

    pub fn build_string(&self, pretty: bool) -> Result<String, String> {
        let doc = self.build();
        if pretty {
            serde_json::to_string_pretty(&doc).map_err(|e| e.to_string())
        } else {
            serde_json::to_string(&doc).map_err(|e| e.to_string())
        }
    }
}
