//! Summation, moments and rounding in the order the published release used.
//!
//! NumPy sums a 1-D array pairwise in blocks of eight; pandas' `groupby`
//! mean is Kahan-compensated and its `std` is Welford's update. Rounding
//! follows NumPy (`rint(x·10ᵈ)/10ᵈ`) for frame values and Python's
//! correctly rounded `round` for scalars written to JSON or text.

/// NumPy pairwise sum (`np.sum` of a contiguous float64 array).
pub fn psum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut s = 0.0_f64;
        for &x in a {
            s += x;
        }
        s
    } else if n <= 128 {
        let mut r = [0.0_f64; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - n % 8 {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut s = (r[0] + r[1]) + (r[2] + r[3]) + ((r[4] + r[5]) + (r[6] + r[7]));
        for &x in &a[i..] {
            s += x;
        }
        s
    } else {
        let m = (n / 2) - (n / 2) % 8;
        psum(&a[..m]) + psum(&a[m..])
    }
}

/// `Series.mean()`: pairwise sum over the non-NaN values.
pub fn mean(a: &[f64]) -> f64 {
    let v: Vec<f64> = a.iter().copied().filter(|x| !x.is_nan()).collect();
    if v.is_empty() { f64::NAN } else { psum(&v) / v.len() as f64 }
}

/// pandas `groupby(...).mean()` of one group: Kahan sum over non-NaN values.
pub fn kahan_mean(a: &[f64]) -> f64 {
    let (mut s, mut c, mut n) = (0.0_f64, 0.0_f64, 0usize);
    for &x in a.iter().filter(|x| !x.is_nan()) {
        let y = x - c;
        let t = s + y;
        c = (t - s) - y;
        s = t;
        n += 1;
    }
    if n == 0 { f64::NAN } else { s / n as f64 }
}

/// pandas `groupby(...).std(ddof)` of one group: Welford's update.
pub fn welford_std(a: &[f64], ddof: usize) -> f64 {
    let (mut n, mut m, mut s2) = (0usize, 0.0_f64, 0.0_f64);
    for &x in a.iter().filter(|x| !x.is_nan()) {
        n += 1;
        let d = x - m;
        m += d / n as f64;
        s2 += d * (x - m);
    }
    if n <= ddof { f64::NAN } else { (s2 / (n - ddof) as f64).sqrt() }
}

/// `np.var(a, ddof)`: two-pass, pairwise sums.
pub fn var(a: &[f64], ddof: usize) -> f64 {
    let n = a.len();
    if n <= ddof {
        return f64::NAN;
    }
    let m = psum(a) / n as f64;
    let d: Vec<f64> = a.iter().map(|x| (x - m) * (x - m)).collect();
    psum(&d) / (n - ddof) as f64
}

/// `np.std(a, ddof)`.
pub fn std(a: &[f64], ddof: usize) -> f64 {
    var(a, ddof).sqrt()
}

/// Linear-interpolated quantile of sorted values (`np.percentile`, pandas `quantile`).
pub fn quantile_sorted(s: &[f64], q: f64) -> f64 {
    if s.is_empty() {
        return f64::NAN;
    }
    let h = (s.len() - 1) as f64 * q;
    let (lo, hi) = (h.floor() as usize, h.ceil() as usize);
    let g = h - lo as f64;
    // NumPy's `_lerp`: a + (b - a)·g, taken from the far end when g ≥ ½.
    let (a, b) = (s[lo], s[hi]);
    let d = b - a;
    if g >= 0.5 { b - d * (1.0 - g) } else { a + d * g }
}

pub fn quantile(a: &[f64], q: f64) -> f64 {
    let mut s: Vec<f64> = a.iter().copied().filter(|x| !x.is_nan()).collect();
    s.sort_by(f64::total_cmp);
    quantile_sorted(&s, q)
}

/// NumPy `round(x, d)`: rint(x·10ᵈ)/10ᵈ, ties to even.
pub fn np_round(x: f64, d: i32) -> f64 {
    let p = 10f64.powi(d);
    if d >= 0 { (x * p).round_ties_even() / p } else { (x / 10f64.powi(-d)).round_ties_even() * 10f64.powi(-d) }
}

/// Python `round(x, d)`: the decimal nearest the exact binary value, ties to even.
pub fn py_round(x: f64, d: usize) -> f64 {
    if !x.is_finite() {
        return x;
    }
    format!("{x:.d$}").parse().unwrap()
}

/// Python `str(float)` / `repr(float)`: shortest round-trip digits, `1.0`, `1e-05`, `1e+16`.
pub fn py_repr(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    // Shortest digits and decimal exponent from Rust's round-trip formatting.
    let e = format!("{x:e}");
    let (mant, exp) = e.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let neg = mant.starts_with('-');
    let digits: String = mant.chars().filter(|c| c.is_ascii_digit()).collect();
    let sign = if neg { "-" } else { "" };
    if (-4..16).contains(&exp) {
        let n = digits.len() as i32;
        let s = if exp >= n - 1 {
            format!("{digits}{}.0", "0".repeat((exp - (n - 1)) as usize))
        } else if exp >= 0 {
            let (i, f) = digits.split_at(exp as usize + 1);
            format!("{i}.{f}")
        } else {
            format!("0.{}{digits}", "0".repeat((-exp - 1) as usize))
        };
        format!("{sign}{s}")
    } else {
        let m = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
        format!("{sign}{m}e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs())
    }
}

/// Python `f"{x:.0f}"` of a float: exact binary value rounded half-even.
pub fn fmt0(x: f64) -> String {
    if x.is_nan() { String::new() } else { format!("{x:.0}") }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repr_matches_python() {
        for (x, s) in [(1.0, "1.0"), (1813.7, "1813.7"), (1e-5, "1e-05"), (0.0001, "0.0001"), (1e16, "1e+16"),
                       (123456789012345.6, "123456789012345.6"), (-2.5, "-2.5"), (0.1 + 0.2, "0.30000000000000004")] {
            assert_eq!(py_repr(x), s);
        }
    }

    #[test]
    fn rounding_modes() {
        assert_eq!(np_round(2.675, 2), 2.68); // the product rounds to 267.5 first
        assert_eq!(py_round(2.675, 2), 2.67); // exact binary value is below the tie
        assert_eq!(np_round(0.5, 0), 0.0);
        assert_eq!(fmt0(2.5), "2");
    }

    #[test]
    fn pairwise_sum_blocks() {
        let a: Vec<f64> = (0..1000).map(|i| (i as f64) * 0.1).collect();
        assert!((psum(&a) - 49950.0).abs() < 1e-9);
        assert_eq!(quantile_sorted(&[1.0, 2.0, 3.0, 4.0], 0.75), 3.25);
    }
}
