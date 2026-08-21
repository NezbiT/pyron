//! Compact segment trie / radix router.
//!
//! Paths are split on `/`. Static segments win over `{param}` which wins over
//! `{*catchall}`. Matching is allocation-light: params are collected into a
//! small `Vec` and converted to a Python dict only at the FFI boundary.

use std::collections::HashMap;

use crate::method::Method;

#[derive(Debug, Default)]
struct Node {
    statics: HashMap<String, Node>,
    param: Option<(String, Box<Node>)>,
    catchall: Option<(String, Box<Node>)>,
    /// method → route id
    routes: HashMap<Method, u32>,
}

#[derive(Debug, Default)]
pub struct RouterInner {
    root: Node,
    /// All methods registered on a path, used for 405 Allow headers.
    path_methods: HashMap<String, Vec<String>>,
    size: u32,
}

#[derive(Debug, Clone)]
pub struct Match {
    pub route_id: u32,
    pub params: Vec<(String, String)>,
}

#[derive(Debug, Clone)]
pub enum FindResult {
    Found(Match),
    MethodNotAllowed { allowed: Vec<String> },
    NotFound,
}

impl RouterInner {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> u32 {
        self.size
    }

    pub fn add(&mut self, method: Method, path: &str, route_id: u32) -> Result<(), String> {
        if !path.starts_with('/') {
            return Err(format!("route path must start with '/': {path}"));
        }
        let segments = split_path(path);
        let mut node = &mut self.root;
        for seg in &segments {
            if let Some(name) = catchall_name(seg) {
                node = node
                    .catchall
                    .get_or_insert_with(|| (name.to_string(), Box::new(Node::default())))
                    .1
                    .as_mut();
            } else if let Some(name) = param_name(seg) {
                let entry = node
                    .param
                    .get_or_insert_with(|| (name.to_string(), Box::new(Node::default())));
                if entry.0 != name {
                    return Err(format!(
                        "conflicting param names at the same position: '{}' vs '{}'",
                        entry.0, name
                    ));
                }
                node = entry.1.as_mut();
            } else {
                node = node.statics.entry((*seg).to_string()).or_default();
            }
        }
        if node.routes.contains_key(&method) {
            return Err(format!("duplicate route: {} {}", method, path));
        }
        node.routes.insert(method, route_id);
        self.path_methods
            .entry(normalize_template(path))
            .or_default()
            .push(method.as_str().to_string());
        self.size += 1;
        Ok(())
    }

    pub fn find(&self, method: Method, path: &str) -> FindResult {
        let segments: Vec<&str> = split_path(path);
        let mut params = Vec::with_capacity(4);
        if let Some(route_id) = walk(&self.root, &segments, 0, &mut params, method) {
            return FindResult::Found(Match { route_id, params });
        }
        // HEAD may fall back to GET (RFC 9110).
        if method == Method::Head {
            params.clear();
            if let Some(route_id) = walk(&self.root, &segments, 0, &mut params, Method::Get) {
                return FindResult::Found(Match { route_id, params });
            }
        }
        // Distinguish 404 vs 405: any method at this path?
        params.clear();
        let allowed = collect_methods(&self.root, &segments, 0);
        if allowed.is_empty() {
            FindResult::NotFound
        } else {
            FindResult::MethodNotAllowed { allowed }
        }
    }

    #[allow(dead_code)]
    pub fn allowed_for_template(&self, path: &str) -> Vec<String> {
        self.path_methods
            .get(&normalize_template(path))
            .cloned()
            .unwrap_or_default()
    }
}

fn walk(
    node: &Node,
    segments: &[&str],
    i: usize,
    params: &mut Vec<(String, String)>,
    method: Method,
) -> Option<u32> {
    if i == segments.len() {
        return node.routes.get(&method).copied();
    }
    let seg = segments[i];

    // 1. Static match — highest priority.
    if let Some(child) = node.statics.get(seg) {
        let mark = params.len();
        if let Some(id) = walk(child, segments, i + 1, params, method) {
            return Some(id);
        }
        params.truncate(mark);
    }

    // 2. Named parameter.
    if let Some((name, child)) = node.param.as_ref() {
        if !seg.is_empty() {
            params.push((name.clone(), seg.to_string()));
            if let Some(id) = walk(child, segments, i + 1, params, method) {
                return Some(id);
            }
            params.pop();
        }
    }

    // 3. Catch-all consumes the rest of the path.
    if let Some((name, child)) = node.catchall.as_ref() {
        let rest = if i < segments.len() {
            segments[i..].join("/")
        } else {
            String::new()
        };
        params.push((name.clone(), rest));
        if let Some(id) = child.routes.get(&method).copied() {
            return Some(id);
        }
        params.pop();
    }

    None
}

fn collect_methods(node: &Node, segments: &[&str], i: usize) -> Vec<String> {
    if i == segments.len() {
        let mut m: Vec<String> = node.routes.keys().map(|k| k.as_str().to_string()).collect();
        m.sort();
        m.dedup();
        return m;
    }
    let seg = segments[i];
    if let Some(child) = node.statics.get(seg) {
        let found = collect_methods(child, segments, i + 1);
        if !found.is_empty() {
            return found;
        }
    }
    if let Some((_, child)) = node.param.as_ref() {
        if !seg.is_empty() {
            let found = collect_methods(child, segments, i + 1);
            if !found.is_empty() {
                return found;
            }
        }
    }
    if let Some((_, child)) = node.catchall.as_ref() {
        let mut m: Vec<String> = child.routes.keys().map(|k| k.as_str().to_string()).collect();
        m.sort();
        m.dedup();
        return m;
    }
    Vec::new()
}

pub fn split_path(path: &str) -> Vec<&str> {
    let trimmed = path.trim_start_matches('/').trim_end_matches('/');
    if trimmed.is_empty() {
        Vec::new()
    } else {
        trimmed.split('/').collect()
    }
}

fn param_name(seg: &str) -> Option<&str> {
    if seg.starts_with('{') && seg.ends_with('}') && !seg.starts_with("{*") {
        Some(&seg[1..seg.len() - 1])
    } else {
        None
    }
}

fn catchall_name(seg: &str) -> Option<&str> {
    if seg.starts_with("{*") && seg.ends_with('}') {
        Some(&seg[2..seg.len() - 1])
    } else {
        None
    }
}

fn normalize_template(path: &str) -> String {
    if path.len() > 1 && path.ends_with('/') {
        path[..path.len() - 1].to_string()
    } else {
        path.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rid(r: &RouterInner, method: Method, path: &str) -> Option<u32> {
        match r.find(method, path) {
            FindResult::Found(m) => Some(m.route_id),
            _ => None,
        }
    }

    #[test]
    fn static_and_param() {
        let mut r = RouterInner::new();
        r.add(Method::Get, "/users/me", 1).unwrap();
        r.add(Method::Get, "/users/{id}", 2).unwrap();
        r.add(Method::Post, "/users", 3).unwrap();
        assert_eq!(rid(&r, Method::Get, "/users/me"), Some(1));
        assert_eq!(rid(&r, Method::Get, "/users/42"), Some(2));
        assert_eq!(rid(&r, Method::Post, "/users"), Some(3));
        match r.find(Method::Get, "/users/42") {
            FindResult::Found(m) => assert_eq!(m.params, vec![("id".into(), "42".into())]),
            _ => panic!("expected match"),
        }
    }

    #[test]
    fn catchall() {
        let mut r = RouterInner::new();
        r.add(Method::Get, "/files/{*path}", 9).unwrap();
        match r.find(Method::Get, "/files/a/b/c.txt") {
            FindResult::Found(m) => {
                assert_eq!(m.route_id, 9);
                assert_eq!(m.params, vec![("path".into(), "a/b/c.txt".into())]);
            }
            _ => panic!("expected catchall"),
        }
    }

    #[test]
    fn method_not_allowed() {
        let mut r = RouterInner::new();
        r.add(Method::Get, "/only-get", 1).unwrap();
        match r.find(Method::Post, "/only-get") {
            FindResult::MethodNotAllowed { allowed } => {
                assert_eq!(allowed, vec!["GET".to_string()]);
            }
            other => panic!("expected 405, got {other:?}"),
        }
    }

    #[test]
    fn head_falls_back_to_get() {
        let mut r = RouterInner::new();
        r.add(Method::Get, "/page", 4).unwrap();
        assert_eq!(rid(&r, Method::Head, "/page"), Some(4));
    }
}
