from ratings.divisions import display_division_label


def test_normalize_division_preserves_womens_labels():
    assert display_division_label("UFC Women's Flyweight Bout") == "Women's Flyweight"
    assert display_division_label("UFC Women's Strawweight Title Bout") == "Women's Strawweight"
    assert display_division_label("UFC Flyweight Bout") == "Flyweight"
