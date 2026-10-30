//! Whole-History Rating coordinate ascent and conditional block variances.
//!
//! Python builds the appearance graph and the age buckets and maps the result back to the Elo
//! scale. The kernel retains the published operation order, including pairwise summation
//! for the per-pass mean.
//!
//! Legend
//!   r    rating of each appearance node, natural scale
//!   o    opponent node of each node
//!   s    score of each node (1, 0.5, 0, or a graded win)
//!   w    bout likelihood weight of each node
//!   ix   node ids grouped by fighter, chronological; fighter f owns ix[pt[f]..pt[f+1]]
//!   gp   days to the fighter's next node, aligned with ix (a fighter's last entry is unused)
//!   bn   age bucket of that transition, aligned with ix; -1 = unknown
//!   w2   Wiener variance per day     ip  1 / anchor prior variance     vg  virtual games
//!   cl   Newton step clip            np  passes per fit                ad  age drift on
//!   ce   re-centre after each pass   nb  number of age buckets         lim drift clip per day
//!   dr   drift per day per age bucket
//!   k    a fighter's node count; p, g, h, a, b, x: win probability, gradient, Hessian diagonal,
//!        system diagonal, off-diagonal and Newton step of that fighter's block

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// numpy's `pairwise_sum` for contiguous float64 (`PW_BLOCKSIZE` 128, eight accumulators).
fn pw(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut t = 0.0;
        for &v in a {
            t += v;
        }
        t
    } else if n <= 128 {
        let mut q = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 {
                q[j] += a[i + j];
            }
            i += 8;
        }
        let mut t = ((q[0] + q[1]) + (q[2] + q[3])) + ((q[4] + q[5]) + (q[6] + q[7]));
        while i < n {
            t += a[i];
            i += 1;
        }
        t
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pw(&a[..n2]) + pw(&a[n2..])
    }
}

/// Symmetric tridiagonal solve, `b` as both sub- and super-diagonal.
/// `c` and `d` are scratch of length at least n, reused across calls.
fn thomas(a: &[f64], b: &[f64], y: &[f64], x: &mut [f64], c: &mut [f64], d: &mut [f64]) {
    let n = a.len();
    if n == 1 {
        x[0] = if a[0] != 0.0 { y[0] / a[0] } else { 0.0 };
        return;
    }
    let mut be = a[0];
    c[0] = b[0] / be;
    d[0] = y[0] / be;
    for i in 1..n - 1 {
        be = a[i] - b[i - 1] * c[i - 1];
        c[i] = b[i] / be;
        d[i] = (y[i] - b[i - 1] * d[i - 1]) / be;
    }
    be = a[n - 1] - b[n - 2] * c[n - 2];
    d[n - 1] = (y[n - 1] - b[n - 2] * d[n - 2]) / be;
    x[n - 1] = d[n - 1];
    for i in (0..n - 1).rev() {
        x[i] = d[i] - c[i] * x[i + 1];
    }
}

fn f64s(v: &[u8]) -> Vec<f64> {
    v.as_chunks::<8>()
        .0
        .iter()
        .map(|c| f64::from_le_bytes(*c))
        .collect()
}

fn i64s(v: &[u8]) -> Vec<i64> {
    v.as_chunks::<8>()
        .0
        .iter()
        .map(|c| i64::from_le_bytes(*c))
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn passes(
    o: &[i64],
    s: &[f64],
    w: &[f64],
    pt: &[i64],
    ix: &[i64],
    gp: &[f64],
    bn: &[i64],
    w2: f64,
    ip: f64,
    vg: f64,
    cl: f64,
    np: usize,
    ad: bool,
    ce: bool,
    nb: usize,
    lim: f64,
) -> (Vec<f64>, Vec<f64>) {
    let n = o.len();
    let nf = pt.len() - 1;
    let mut r = vec![0.0f64; n];
    let mut dr = vec![0.0f64; nb];
    let tot = np * if ad { 2 } else { 1 };
    // The Wiener precision of each transition depends only on the schedule, so it is
    // computed once; 1 / (w2 * gap) gives the same bits on every pass.
    let iw: Vec<f64> = gp.iter().map(|&q| 1.0 / (w2 * q)).collect();
    let km = (0..nf)
        .map(|f| (pt[f + 1] - pt[f]) as usize)
        .max()
        .unwrap_or(0);
    let z = || vec![0.0f64; km];
    let (mut rk, mut ok, mut p, mut g, mut h, mut a, mut b, mut x) =
        (z(), z(), z(), z(), z(), z(), z(), z());
    let (mut e, mut c, mut d) = (z(), z(), z());
    for pass in 0..tot {
        for f in 0..nf {
            let lo = pt[f] as usize;
            let nd = &ix[lo..pt[f + 1] as usize];
            let k = nd.len();
            if k == 0 {
                continue;
            }
            for j in 0..k {
                let u = nd[j] as usize;
                rk[j] = r[u];
                ok[j] = r[o[u] as usize];
            }
            for j in 0..k {
                let u = nd[j] as usize;
                p[j] = 1.0 / (1.0 + (-(rk[j] - ok[j])).exp());
                g[j] = w[u] * (s[u] - p[j]);
                h[j] = w[u] * (-p[j] * (1.0 - p[j]));
            }
            let an = ip / k as f64;
            for j in 0..k {
                g[j] -= rk[j] * an;
                h[j] -= an;
            }
            if vg > 0.0 {
                let v = vg / k as f64;
                for j in 0..k {
                    let p0 = 1.0 / (1.0 + (-rk[j]).exp());
                    g[j] += v * (0.5 - p0);
                    h[j] -= v * p0 * (1.0 - p0);
                }
            }
            if k > 1 {
                // numpy applies g[:-1] += ... to the whole slice before g[1:] -= ..., so each
                // interior entry adds its own transition first and subtracts the previous one.
                let iv = &iw[lo..lo + k - 1];
                for j in 0..k - 1 {
                    let mut res = rk[j + 1] - rk[j];
                    if ad {
                        let q = bn[lo + j];
                        let ex = if q >= 0 {
                            dr[q as usize] * gp[lo + j]
                        } else {
                            0.0
                        };
                        res -= ex;
                    }
                    e[j] = res * iv[j];
                }
                for j in 0..k - 1 {
                    g[j] += e[j];
                }
                for j in 0..k - 1 {
                    g[j + 1] -= e[j];
                }
                for j in 0..k - 1 {
                    h[j] -= iv[j];
                }
                for j in 0..k - 1 {
                    h[j + 1] -= iv[j];
                }
                for j in 0..k - 1 {
                    b[j] = -iv[j];
                }
            }
            for j in 0..k {
                a[j] = -h[j];
            }
            thomas(
                &a[..k],
                &b[..k.saturating_sub(1)],
                &g[..k],
                &mut x[..k],
                &mut c,
                &mut d,
            );
            for j in 0..k {
                r[nd[j] as usize] = rk[j] + x[j].clamp(-cl, cl);
            }
        }
        if ce {
            let m = pw(&r) / n as f64;
            for v in r.iter_mut() {
                *v -= m;
            }
        }
        if ad && pass == np - 1 {
            let mut cs = vec![0.0f64; nb];
            let mut ds = vec![0.0f64; nb];
            for f in 0..nf {
                let lo = pt[f] as usize;
                let nd = &ix[lo..pt[f + 1] as usize];
                let k = nd.len();
                if k < 2 {
                    continue;
                }
                for q in 0..nb {
                    let mut ch = vec![];
                    let mut dy = vec![];
                    for j in 0..k - 1 {
                        if bn[lo + j] == q as i64 {
                            ch.push(r[nd[j + 1] as usize] - r[nd[j] as usize]);
                            dy.push(gp[lo + j]);
                        }
                    }
                    if !ch.is_empty() {
                        cs[q] += pw(&ch);
                        ds[q] += pw(&dy);
                    }
                }
            }
            let raw: Vec<f64> = (0..nb)
                .map(|q| if ds[q] > 0.0 { cs[q] / ds[q] } else { 0.0 })
                .collect();
            let bl = if ds[0] > 0.0 { raw[0] } else { 0.0 };
            for q in 0..nb {
                let t = if ds[q] == 0.0 { 0.0 } else { raw[q] - bl };
                dr[q] = t.clamp(-lim, lim);
            }
            r.fill(0.0);
        }
    }
    (r, dr)
}

/// Conditional block variances from the per-fighter Hessian, holding opponents fixed.
/// Meurant's forward/backward pivot recurrences give the inverse diagonal in O(n).
#[allow(clippy::too_many_arguments)]
fn variances(
    r: &[f64],
    o: &[i64],
    w: &[f64],
    pt: &[i64],
    ix: &[i64],
    gp: &[f64],
    w2: f64,
    ip: f64,
    vg: f64,
) -> Vec<f64> {
    let mut out = vec![0.0; r.len()];
    for f in 0..pt.len() - 1 {
        let lo = pt[f] as usize;
        let nd = &ix[lo..pt[f + 1] as usize];
        let k = nd.len();
        if k == 0 {
            continue;
        }
        let mut a = vec![0.0; k];
        let mut b = vec![0.0; k.saturating_sub(1)];
        for j in 0..k {
            let n = nd[j] as usize;
            let p = 1.0 / (1.0 + (-(r[n] - r[o[n] as usize])).exp());
            let mut h = w[n] * (-p * (1.0 - p)) - ip / k as f64;
            if vg > 0.0 {
                let p0 = 1.0 / (1.0 + (-r[n]).exp());
                h -= (vg / k as f64) * p0 * (1.0 - p0);
            }
            if j > 0 {
                h -= 1.0 / (w2 * gp[lo + j - 1]);
            }
            if j + 1 < k {
                let iv = 1.0 / (w2 * gp[lo + j]);
                h -= iv;
                b[j] = -iv;
            }
            a[j] = -h;
        }
        let mut delta = a.clone();
        let mut lambda = a.clone();
        for j in 1..k {
            delta[j] = a[j] - b[j - 1].powi(2) / delta[j - 1];
        }
        for j in (0..k - 1).rev() {
            lambda[j] = a[j] - b[j].powi(2) / lambda[j + 1];
        }
        for j in 0..k {
            out[nd[j] as usize] = if k == 1 {
                1.0 / a[j]
            } else {
                1.0 / (delta[j] + lambda[j] - a[j])
            };
        }
    }
    out
}

/// Arrays arrive and return as little-endian float64 / int64 bytes.
#[pyfunction]
#[pyo3(signature = (o, s, w, pt, ix, gp, bn, w2, ip, vg, cl, np, ad, ce, nb, lim, return_variance=false))]
#[allow(clippy::too_many_arguments)]
fn fit<'py>(
    py: Python<'py>,
    o: &[u8],
    s: &[u8],
    w: &[u8],
    pt: &[u8],
    ix: &[u8],
    gp: &[u8],
    bn: &[u8],
    w2: f64,
    ip: f64,
    vg: f64,
    cl: f64,
    np: usize,
    ad: bool,
    ce: bool,
    nb: usize,
    lim: f64,
    return_variance: bool,
) -> PyResult<(
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
)> {
    let (o, s, w, pt, ix, gp, bn) = (
        i64s(o),
        f64s(s),
        f64s(w),
        i64s(pt),
        i64s(ix),
        f64s(gp),
        i64s(bn),
    );
    let n = o.len();
    if s.len() != n
        || w.len() != n
        || ix.len() != n
        || gp.len() != n
        || bn.len() != n
        || pt.is_empty()
    {
        return Err(PyValueError::new_err("array lengths disagree"));
    }
    if ad && np == 0 {
        return Err(PyValueError::new_err("age drift needs at least one pass"));
    }
    let (r, dr, var) = py.detach(|| {
        let (r, dr) = passes(
            &o, &s, &w, &pt, &ix, &gp, &bn, w2, ip, vg, cl, np, ad, ce, nb, lim,
        );
        let var = if return_variance {
            variances(&r, &o, &w, &pt, &ix, &gp, w2, ip, vg)
        } else {
            vec![]
        };
        (r, dr, var)
    });
    let rb: Vec<u8> = r.iter().flat_map(|v| v.to_le_bytes()).collect();
    let db: Vec<u8> = dr.iter().flat_map(|v| v.to_le_bytes()).collect();
    let vb: Vec<u8> = var.iter().flat_map(|v| v.to_le_bytes()).collect();
    Ok((
        PyBytes::new(py, &rb),
        PyBytes::new(py, &db),
        PyBytes::new(py, &vb),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tridiagonal_known_solution() {
        let mut x = [0.0; 3];
        thomas(
            &[2.0, 3.0, 2.0],
            &[1.0, 1.0],
            &[1.0, 0.0, 3.0],
            &mut x,
            &mut [0.0; 3],
            &mut [0.0; 3],
        );
        for (actual, expected) in x.iter().zip([1.0, -1.0, 2.0]) {
            assert!((actual - expected).abs() < 1e-12);
        }
    }
}

#[pymodule]
fn whr_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fit, m)?)
}
