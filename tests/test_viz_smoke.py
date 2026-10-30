from analysis.viz import normalize_division


def test_normalize_division_preserves_womens_labels():
    assert normalize_division("UFC Women's Flyweight Bout") == "Women's Flyweight"
    assert normalize_division("UFC Women's Strawweight Title Bout") == "Women's Strawweight"
    assert normalize_division("UFC Flyweight Bout") == "Flyweight"
