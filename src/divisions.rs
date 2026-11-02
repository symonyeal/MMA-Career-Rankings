//! Division labels, the women's fold, and the gender split of a fighter table.
//!
//! One women's division is billed three ways in the corpus (UFCStats
//! "Women's Flyweight", Sherdog's bare "Flyweight", "125lb Catchweight");
//! `womens` folds them onto one pool, so a woman's career is scored against
//! one contender line whatever source billed her bouts.

use std::sync::OnceLock;

use regex::Regex;

/// `DIVISION_LABELS`, matched in this order by `normalize`.
pub const LABELS: [&str; 14] = [
    "Women's Strawweight",
    "Women's Flyweight",
    "Women's Bantamweight",
    "Women's Featherweight",
    "Light Heavyweight",
    "Heavyweight",
    "Middleweight",
    "Welterweight",
    "Lightweight",
    "Featherweight",
    "Bantamweight",
    "Flyweight",
    "Catch Weight",
    "Open Weight",
];

/// Men's classes with their limit in pounds, light to heavy (`MEN_LIMIT_LB`).
pub const MEN_LIMIT_LB: [(&str, u32); 9] = [
    ("Strawweight", 115),
    ("Flyweight", 125),
    ("Bantamweight", 135),
    ("Featherweight", 145),
    ("Lightweight", 155),
    ("Welterweight", 170),
    ("Middleweight", 185),
    ("Light Heavyweight", 205),
    ("Heavyweight", 265),
];

const WOMEN_LIMIT_LB: [(u32, &str); 5] = [
    (105, "Women's Atomweight"),
    (115, "Women's Strawweight"),
    (125, "Women's Flyweight"),
    (135, "Women's Bantamweight"),
    (145, "Women's Featherweight"),
];

/// Display divisions and their short codes (`DIV_SHORT`, in this order).
pub const SHORT: [(&str, &str); 15] = [
    ("Strawweight", "STW"),
    ("Flyweight", "FLY"),
    ("Bantamweight", "BW"),
    ("Featherweight", "FW"),
    ("Lightweight", "LW"),
    ("Welterweight", "WW"),
    ("Middleweight", "MW"),
    ("Light Heavyweight", "LHW"),
    ("Heavyweight", "HW"),
    ("Women's Strawweight", "W.STW"),
    ("Women's Flyweight", "W.FLY"),
    ("Women's Bantamweight", "W.BW"),
    ("Women's Featherweight", "W.FW"),
    ("Catch Weight", "CW"),
    ("Open Weight", "OW"),
];

fn squash(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// `normalize_division_label`: UFCStats weight-class text to a stable label; `None` for blank.
pub fn normalize(weight_class: &str) -> Option<String> {
    let text = squash(weight_class);
    let cleaned = text
        .replace("UFC ", "")
        .replace("Interim ", "")
        .replace(" Title Bout", "")
        .replace(" Bout", "")
        .trim()
        .to_string();
    let lower = cleaned.to_lowercase();
    LABELS
        .iter()
        .find(|l| lower.contains(&l.to_lowercase()))
        .map(|l| l.to_string())
        .or((!cleaned.is_empty()).then_some(cleaned))
}

/// `display_division_label`: the most specific display division named in the text, else the stripped text.
pub fn display(weight_class: &str) -> String {
    let w = weight_class
        .replace("UFC ", "")
        .replace(" Title Bout", "")
        .replace(" Bout", "")
        .trim()
        .to_string();
    let lower = w.to_lowercase();
    let mut by_len: Vec<&str> = SHORT.iter().map(|p| p.0).collect();
    by_len.sort_by_key(|d| std::cmp::Reverse(d.len()));
    by_len
        .into_iter()
        .find(|d| lower.contains(&d.to_lowercase()))
        .map(str::to_string)
        .unwrap_or(w)
}

/// `womens_division_label`: any billing of a woman's bout onto one women's division.
pub fn womens(division: &str) -> Option<String> {
    static LB: OnceLock<Regex> = OnceLock::new();
    if division.trim().is_empty() {
        return None;
    }
    let text = squash(division);
    if text.starts_with("Women's") {
        return Some(text);
    }
    if let Some((_, l)) = WOMEN_LIMIT_LB
        .iter()
        .find(|(_, l)| l.strip_prefix("Women's ") == Some(text.as_str()))
    {
        return Some(l.to_string());
    }
    if let Some(m) = LB
        .get_or_init(|| Regex::new(r"(?i)(\d{2,3})\s*lb").unwrap())
        .captures(&text)
    {
        let lb: u32 = m[1].parse().unwrap();
        return Some(
            WOMEN_LIMIT_LB
                .iter()
                .find(|(x, _)| lb <= *x)
                .map_or("Women's Openweight", |p| p.1)
                .to_string(),
        );
    }
    // RIZIN bills its women's openweight bouts as Heavyweight and Light Heavyweight.
    const OPEN: [&str; 9] = [
        "Heavyweight",
        "Light Heavyweight",
        "Middleweight",
        "Welterweight",
        "Lightweight",
        "Open Weight",
        "Openweight",
        "Catch Weight",
        "Catchweight",
    ];
    OPEN.contains(&text.as_str())
        .then(|| "Women's Openweight".to_string())
}

/// `female_mask`: a gender label reading F (and not M); blank is not female.
pub fn female(gender: &str) -> bool {
    let g = gender.trim().to_uppercase();
    g.starts_with('F') && !g.starts_with('M')
}

/// `division_labels` / `division_column`: the career pool or shown division of one fighter,
/// women's divisions folded, `"W "` + raw when unplaceable; `None` when the division is unknown.
pub fn pool(division: &str, gender: &str) -> Option<String> {
    if division.is_empty() {
        None
    } else if gender.trim().to_uppercase().starts_with('F') {
        Some(womens(division).unwrap_or_else(|| format!("W {division}")))
    } else {
        Some(division.to_string())
    }
}

/// `is_real_ufc_title_bout`: a UFC undisputed or interim title bout; TUF, Road to UFC and tournament finals are not.
pub fn ufc_title(weight_class: &str) -> bool {
    let t = squash(weight_class)
        .to_lowercase()
        .replace("titlebout", "title bout");
    t.contains("title bout")
        && ![
            "ultimate fighter",
            "road to ufc",
            "tuf nations",
            "tournament",
        ]
        .iter()
        .any(|x| t.contains(x))
        && t.starts_with("ufc ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn labels() {
        assert_eq!(
            normalize("UFC Interim Lightweight Title Bout").as_deref(),
            Some("Lightweight")
        );
        assert_eq!(
            normalize("Women's Flyweight Bout").as_deref(),
            Some("Women's Flyweight")
        );
        assert_eq!(normalize("  ").as_deref(), None);
        assert_eq!(womens("Flyweight").as_deref(), Some("Women's Flyweight"));
        assert_eq!(
            womens("125lb Catchweight").as_deref(),
            Some("Women's Flyweight")
        );
        assert_eq!(womens("Heavyweight").as_deref(), Some("Women's Openweight"));
        assert_eq!(
            display("UFC Women's Flyweight Title Bout"),
            "Women's Flyweight"
        );
    }
}
