//! README narrative paragraphs: splice a regenerated paragraph in place, wrapped at 79 columns.
//!
//! The wrap reproduces Python's `textwrap.fill` with its defaults, which the published README was
//! written with: words break at whitespace and after a hyphen that follows two letters (or a
//! letter-hyphen-letter) and precedes a letter, and lines fill greedily.

/// Width of a wrapped README line.
pub const WIDTH: usize = 79;

/// Chunks of `s`: whitespace runs, and words cut after their breakable hyphens.
fn chunks(s: &str) -> Vec<String> {
    let c: Vec<char> = s.chars().collect();
    let letter = |i: usize| c.get(i).is_some_and(|x| x.is_alphabetic());
    let mut out = Vec::new();
    let mut a = 0;
    while a < c.len() {
        let ws = c[a].is_whitespace();
        let mut b = a + 1;
        while b < c.len() && c[b].is_whitespace() == ws {
            // A word may break after `-` when the hyphen follows `ll` or `l-l` and precedes `l` or `l-l`.
            if !ws && c[b - 1] == '-' && b >= 3 {
                let after =
                    letter(b) && (letter(b + 1) || (c.get(b + 1) == Some(&'-') && letter(b + 2)));
                let before = (letter(b - 2) && letter(b - 3))
                    || (b >= 4 && letter(b - 2) && c[b - 3] == '-' && letter(b - 4));
                if before && after {
                    break;
                }
            }
            b += 1;
        }
        out.push(c[a..b].iter().collect());
        a = b;
    }
    out
}

/// `textwrap.fill(s, width=w)` for text without tabs or words longer than `w`.
pub fn fill(s: &str, w: usize) -> String {
    let flat: String = s
        .chars()
        .map(|x| if x.is_whitespace() { ' ' } else { x })
        .collect();
    let mut lines: Vec<String> = Vec::new();
    let mut line: Vec<String> = Vec::new();
    let mut n = 0;
    for k in chunks(&flat) {
        let blank = k.trim().is_empty();
        if line.is_empty() && blank {
            continue;
        }
        let m = k.chars().count();
        if n + m > w {
            if line.last().is_some_and(|x| x.trim().is_empty()) {
                line.pop();
            }
            lines.push(line.concat());
            line.clear();
            n = 0;
            if blank {
                continue;
            }
        }
        line.push(k);
        n += m;
    }
    if line.last().is_some_and(|x| x.trim().is_empty()) {
        line.pop();
    }
    if !line.is_empty() {
        lines.push(line.concat());
    }
    lines.join("\n")
}

/// Replace the one paragraph of `t` that starts with `start` (it runs to the next blank line) by
/// `value`. The old line breaks stay when the words are unchanged.
pub fn splice(t: &str, start: &str, value: &str) -> Result<String, String> {
    let at: Vec<usize> = t.match_indices(start).map(|(i, _)| i).collect();
    let ends: Vec<usize> = at
        .iter()
        .filter_map(|&i| t[i..].find("\n\n").map(|e| i + e))
        .collect();
    if ends.len() != 1 {
        return Err(format!(
            "expected one README paragraph starting {start:?}; found {}",
            ends.len()
        ));
    }
    let (a, b) = (at[0], ends[0]);
    let old: Vec<&str> = t[a..b].split_whitespace().collect();
    if old.join(" ") == value {
        return Ok(t.to_string());
    }
    Ok(format!("{}{}{}", &t[..a], fill(value, WIDTH), &t[b..]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hyphens_break_between_letters_only() {
        let k = chunks("St-Pierre's 60th-best 83-point");
        assert_eq!(
            k,
            ["St-", "Pierre's", " ", "60th-", "best", " ", "83-point"]
        );
    }

    #[test]
    fn published_paragraph_round_trips() {
        let p = "**The score is a points total, not a ratio.** Jon Jones's 1,814 against Georges\n\
St-Pierre's 1,564 does not mean Jones was 16% better. It means his three parts\n\
add up to more points: title 617 against 482, résumé 812 against 777, skill 385\n\
against 304. Most of the résumé gap is two elite wins: Daniel Cormier at 334\n\
points above the line and Ciryl Gane at 261, where St-Pierre's best was Sean\n\
Sherk at 189. For who was better at their best, read Prime: 2,193 against\n\
2,110, an 83-point edge, which the rating turns into about a 62% chance of\n\
winning.";
        let v: Vec<&str> = p.split_whitespace().collect();
        assert_eq!(fill(&v.join(" "), WIDTH), p);
    }
}
