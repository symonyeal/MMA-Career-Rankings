//! JSON as Python's `json.dumps(o, separators=(",", ":"), ensure_ascii=False)` writes it.
//!
//! Floats print as Python's `repr` (`1.0`, `1e-05`), integers without a
//! point; `num` applies the site's rounding rule (`build_site.plain`) first:
//! non-finite → null, `nd = 0` → the integer `round(x)`, else `round(x, nd)`.

use crate::stats::{py_repr, py_round};

#[derive(Clone, Debug, PartialEq)]
pub enum J {
    Null,
    Bool(bool),
    Int(i64),
    Num(f64),
    Str(String),
    Arr(Vec<J>),
    Obj(Vec<(String, J)>),
}

/// `plain(x, nd)` of one float.
pub fn num(x: f64, nd: usize) -> J {
    if !x.is_finite() {
        J::Null
    } else if nd == 0 {
        J::Int(x.round_ties_even() as i64)
    } else {
        J::Num(py_round(x, nd))
    }
}

/// `plain(x, nd)` of a missing-or-float value.
pub fn opt(x: Option<f64>, nd: usize) -> J {
    x.map_or(J::Null, |x| num(x, nd))
}

pub fn s(x: &str) -> J {
    J::Str(x.to_string())
}

/// A string, null when empty (the snapshot's missing text).
pub fn opt_s(x: &str) -> J {
    if x.is_empty() {
        J::Null
    } else {
        s(x)
    }
}

/// A pandas integer column after a reindex: integers while complete, floats once any value is missing.
pub fn ints(v: &[Option<i64>], nd: usize) -> J {
    if v.iter().all(Option::is_some) {
        J::Arr(v.iter().map(|x| J::Int(x.unwrap())).collect())
    } else {
        J::Arr(v.iter().map(|x| opt(x.map(|x| x as f64), nd)).collect())
    }
}

impl From<&serde_json::Value> for J {
    fn from(v: &serde_json::Value) -> J {
        use serde_json::Value as V;
        match v {
            V::Null => J::Null,
            V::Bool(b) => J::Bool(*b),
            V::Number(n) => n
                .as_i64()
                .map_or_else(|| J::Num(n.as_f64().unwrap()), J::Int),
            V::String(x) => J::Str(x.clone()),
            V::Array(a) => J::Arr(a.iter().map(J::from).collect()),
            V::Object(o) => J::Obj(o.iter().map(|(k, v)| (k.clone(), J::from(v))).collect()),
        }
    }
}

impl J {
    pub fn dump(&self) -> String {
        let mut out = String::new();
        self.write(&mut out);
        out
    }

    fn write(&self, out: &mut String) {
        match self {
            J::Null => out.push_str("null"),
            J::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            J::Int(i) => out.push_str(&i.to_string()),
            J::Num(x) if x.is_finite() => out.push_str(&py_repr(*x)),
            J::Num(x) => out.push_str(if x.is_nan() {
                "NaN"
            } else if *x > 0.0 {
                "Infinity"
            } else {
                "-Infinity"
            }),
            J::Str(x) => quote(x, out),
            J::Arr(a) => {
                out.push('[');
                for (i, v) in a.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    v.write(out);
                }
                out.push(']');
            }
            J::Obj(o) => {
                out.push('{');
                for (i, (k, v)) in o.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    quote(k, out);
                    out.push(':');
                    v.write(out);
                }
                out.push('}');
            }
        }
    }
}

fn quote(x: &str, out: &mut String) {
    out.push('"');
    for c in x.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_dumps() {
        let v = J::Obj(vec![
            (
                "a".into(),
                J::Arr(vec![
                    num(1.0, 1),
                    num(0.125, 2),
                    num(2.5, 0),
                    num(f64::NAN, 1),
                    J::Int(3),
                ]),
            ),
            ("é\"".into(), s("x\ny")),
        ]);
        assert_eq!(v.dump(), r#"{"a":[1.0,0.12,2,null,3],"é\"":"x\ny"}"#);
    }
}
