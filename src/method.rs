use std::fmt;

/// HTTP methods the radix router matches on.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Method {
    Get,
    Post,
    Put,
    Patch,
    Delete,
    Head,
    Options,
    Trace,
}

impl Method {
    pub fn parse(raw: &str) -> Option<Self> {
        // Fast path: uppercase ASCII without allocating.
        match raw.len() {
            3 => {
                let b = raw.as_bytes();
                if eq_ignore_ascii(b, b"GET") {
                    Some(Self::Get)
                } else if eq_ignore_ascii(b, b"PUT") {
                    Some(Self::Put)
                } else {
                    None
                }
            }
            4 => {
                let b = raw.as_bytes();
                if eq_ignore_ascii(b, b"POST") {
                    Some(Self::Post)
                } else if eq_ignore_ascii(b, b"HEAD") {
                    Some(Self::Head)
                } else {
                    None
                }
            }
            5 => {
                let b = raw.as_bytes();
                if eq_ignore_ascii(b, b"PATCH") {
                    Some(Self::Patch)
                } else if eq_ignore_ascii(b, b"TRACE") {
                    Some(Self::Trace)
                } else {
                    None
                }
            }
            6 => {
                if eq_ignore_ascii(raw.as_bytes(), b"DELETE") {
                    Some(Self::Delete)
                } else {
                    None
                }
            }
            7 => {
                if eq_ignore_ascii(raw.as_bytes(), b"OPTIONS") {
                    Some(Self::Options)
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Get => "GET",
            Self::Post => "POST",
            Self::Put => "PUT",
            Self::Patch => "PATCH",
            Self::Delete => "DELETE",
            Self::Head => "HEAD",
            Self::Options => "OPTIONS",
            Self::Trace => "TRACE",
        }
    }
}

impl fmt::Display for Method {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

fn eq_ignore_ascii(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b.iter()).all(|(x, y)| x.eq_ignore_ascii_case(y))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_mixed_case() {
        assert_eq!(Method::parse("get"), Some(Method::Get));
        assert_eq!(Method::parse("POST"), Some(Method::Post));
        assert_eq!(Method::parse("Options"), Some(Method::Options));
        assert_eq!(Method::parse("NOPE"), None);
    }
}
