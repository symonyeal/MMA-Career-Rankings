//! One error type: a message that names the file, row or fighter it concerns.

use std::fmt;

#[derive(Debug, PartialEq)]
pub struct Error(pub String);

impl Error {
    /// `context: message`, the context being a file path, a table or a fighter.
    pub fn at(context: impl fmt::Display, message: impl fmt::Display) -> Error {
        Error(format!("{context}: {message}"))
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}
