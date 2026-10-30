//! Glicko-2 scalar updates in the published numerical operation order.
//! Derived from Heungsub Lee's BSD-licensed glicko2; the notice is in LICENSE.
//! mu/phi are on the external Glicko scale; sigma is dimensionless volatility.
//! A series item is (score, opponent mu, opponent phi, likelihood weight).
use pyo3::prelude::*;

const PI: f64 = std::f64::consts::PI;
const RATIO: f64 = 173.7178;

#[cfg(windows)]
#[link(name = "ucrt")]
extern "C" {
    #[link_name = "pow"]
    fn c_pow(x: f64, y: f64) -> f64;
    #[link_name = "exp"]
    fn c_exp(x: f64) -> f64;
    #[link_name = "sqrt"]
    fn c_sqrt(x: f64) -> f64;
    #[link_name = "log"]
    fn c_log(x: f64) -> f64;
}

#[cfg(not(windows))]
#[link(name = "m")]
extern "C" {
    #[link_name = "pow"]
    fn c_pow(x: f64, y: f64) -> f64;
    #[link_name = "exp"]
    fn c_exp(x: f64) -> f64;
    #[link_name = "sqrt"]
    fn c_sqrt(x: f64) -> f64;
    #[link_name = "log"]
    fn c_log(x: f64) -> f64;
}

#[inline]
fn pow(x: f64, y: f64) -> f64 {
    // CPython calls the C routine at runtime. LLVM may replace pow(x, 2)
    // with x*x, whose last bit can differ from that routine's result.
    unsafe { c_pow(x, std::hint::black_box(y)) }
}

#[inline]
fn exp(x: f64) -> f64 {
    unsafe { c_exp(std::hint::black_box(x)) }
}

#[inline]
fn sqrt(x: f64) -> f64 {
    unsafe { c_sqrt(x) }
}

#[inline]
fn log(x: f64) -> f64 {
    unsafe { c_log(x) }
}

fn determine_sigma(
    phi: f64,
    sigma: f64,
    difference: f64,
    variance: f64,
    tau: f64,
    epsilon: f64,
) -> f64 {
    let difference_squared = pow(difference, 2.0);
    let alpha = log(pow(sigma, 2.0));
    let f = |x: f64| {
        let tmp = pow(phi, 2.0) + variance + exp(x);
        let a = exp(x) * (difference_squared - tmp) / (2.0 * pow(tmp, 2.0));
        let b = (x - alpha) / pow(tau, 2.0);
        a - b
    };

    let mut a = alpha;
    let mut b = if difference_squared > pow(phi, 2.0) + variance {
        log(difference_squared - pow(phi, 2.0) - variance)
    } else {
        let mut k = 1.0;
        let mut bound = alpha - k * sqrt(pow(tau, 2.0));
        while f(bound) < 0.0 {
            k += 1.0;
            bound = alpha - k * sqrt(pow(tau, 2.0));
        }
        bound
    };
    let mut f_a = f(a);
    let mut f_b = f(b);
    while (b - a).abs() > epsilon {
        let c = a + (a - b) * f_a / (f_b - f_a);
        let f_c = f(c);
        if f_c * f_b < 0.0 {
            a = b;
            f_a = f_b;
        } else {
            f_a /= 2.0;
        }
        b = c;
        f_b = f_c;
    }
    pow(exp(1.0), a / 2.0)
}

fn update(
    mu: f64,
    phi: f64,
    sigma: f64,
    series: &[(f64, f64, f64, f64)],
    center: f64,
    tau: f64,
    epsilon: f64,
) -> (f64, f64, f64) {
    let rating_mu = (mu - center) / RATIO;
    let rating_phi = phi / RATIO;
    if series.is_empty() {
        let phi_star = sqrt(pow(rating_phi, 2.0) + pow(sigma, 2.0));
        return (rating_mu * RATIO + center, phi_star * RATIO, sigma);
    }

    let mut variance_inv = 0.0;
    let mut difference = 0.0;
    for &(score, other_mu, other_phi, weight) in series {
        if weight == 0.0 {
            continue;
        }
        let other_mu = (other_mu - center) / RATIO;
        let other_phi = other_phi / RATIO;
        let impact = 1.0 / sqrt(1.0 + (3.0 * pow(other_phi, 2.0)) / pow(PI, 2.0));
        let expected = 1.0 / (1.0 + exp(-impact * (rating_mu - other_mu)));
        variance_inv += weight * pow(impact, 2.0) * expected * (1.0 - expected);
        difference += weight * impact * (score - expected);
    }
    if variance_inv == 0.0 {
        let phi_star = sqrt(pow(rating_phi, 2.0) + pow(sigma, 2.0));
        return (rating_mu * RATIO + center, phi_star * RATIO, sigma);
    }
    difference /= variance_inv;
    let variance = 1.0 / variance_inv;
    let sigma = determine_sigma(rating_phi, sigma, difference, variance, tau, epsilon);
    let phi_star = sqrt(pow(rating_phi, 2.0) + pow(sigma, 2.0));
    let phi = 1.0 / sqrt(1.0 / pow(phi_star, 2.0) + 1.0 / variance);
    let mu = rating_mu + pow(phi, 2.0) * (difference / variance);
    (mu * RATIO + center, phi * RATIO, sigma)
}

#[pyfunction]
fn rate(
    mu: f64,
    phi: f64,
    sigma: f64,
    series: Vec<(f64, f64, f64, f64)>,
    center: f64,
    tau: f64,
    epsilon: f64,
) -> (f64, f64, f64) {
    update(mu, phi, sigma, &series, center, tau, epsilon)
}

#[pyfunction]
fn inflate(mu: f64, phi: f64, sigma: f64, center: f64, periods: usize) -> (f64, f64, f64) {
    let mut current_mu = mu;
    let mut current_phi = phi;
    for _ in 0..periods {
        current_mu = (current_mu - center) / RATIO * RATIO + center;
        let scaled_phi = current_phi / RATIO;
        let phi_star = sqrt(pow(scaled_phi, 2.0) + pow(sigma, 2.0));
        current_phi = phi_star * RATIO;
    }
    (current_mu, current_phi, sigma)
}

#[pymodule]
fn rating_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rate, m)?)?;
    m.add_function(wrap_pyfunction!(inflate, m)?)?;
    Ok(())
}
