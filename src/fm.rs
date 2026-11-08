//! Transcendental functions from the pure-Rust `libm` crate.
//!
//! The platform C library rounds the last bit differently on Windows (UCRT) and Linux (glibc),
//! so ratings computed with it differed between the two. These functions run the same code on
//! every target. `sqrt`, `mul_add` and the rounding functions are correctly rounded everywhere
//! and stay as `f64` methods.

pub fn exp(x: f64) -> f64 {
    libm::exp(x)
}

pub fn ln(x: f64) -> f64 {
    libm::log(x)
}

/// `ln(1 + x)`.
pub fn ln_1p(x: f64) -> f64 {
    libm::log1p(x)
}

pub fn pow(x: f64, y: f64) -> f64 {
    libm::pow(x, y)
}
