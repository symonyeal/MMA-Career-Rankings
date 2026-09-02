"""The shared page store: what a reader stores is what a reader gets back."""
from __future__ import annotations

import gzip

import pytest

from loaders.page_cache import STORE_NAME, PageCache, fold_in_loose_files, open_cache


PAGE = "<html><body>Ünïcode • 東京 <p>fight card</p></body></html>"


def test_a_stored_page_reads_back_byte_for_byte(tmp_path):
    cache = open_cache(tmp_path)
    cache.put("events", "4088", PAGE)
    assert cache.get("events", "4088") == PAGE


def test_a_page_never_stored_is_none_rather_than_an_error(tmp_path):
    assert open_cache(tmp_path).get("events", "never-fetched") is None


def test_kinds_do_not_collide_on_a_shared_key(tmp_path):
    cache = open_cache(tmp_path)
    cache.put("events", "17", "event page")
    cache.put("fighters", "17", "fighter page")
    assert cache.get("events", "17") == "event page"
    assert cache.get("fighters", "17") == "fighter page"


def test_refetching_a_page_replaces_it_rather_than_duplicating_it(tmp_path):
    cache = open_cache(tmp_path)
    cache.put("events", "1", "first")
    cache.put("events", "1", "second")
    assert cache.get("events", "1") == "second"
    assert cache.counts() == {"events": 1}


def test_a_numeric_key_and_its_text_form_are_one_page(tmp_path):
    """Callers pass ids from parsed HTML and from parquet, so both shapes arrive."""
    cache = open_cache(tmp_path)
    cache.put("fighters", 4088, "page")
    assert cache.get("fighters", "4088") == "page"
    assert cache.has("fighters", 4088)


def test_the_store_lives_inside_the_cache_directory(tmp_path):
    open_cache(tmp_path).put("events", "1", "x")
    assert (tmp_path / STORE_NAME).is_file()
    # One file for the whole cache is the point; WAL sidecars are transient.
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith(STORE_NAME)) == []


def test_an_already_open_store_is_passed_through_not_reopened(tmp_path):
    cache = open_cache(tmp_path)
    assert open_cache(cache) is cache


def test_items_and_keys_read_every_page_of_one_kind_in_order(tmp_path):
    cache = open_cache(tmp_path)
    for key in ("30", "10", "20"):
        cache.put("events", key, f"page {key}")
    assert cache.keys("events") == ["10", "20", "30"]
    assert [text for _, text in cache.items("events")] == ["page 10", "page 20", "page 30"]
    assert cache.keys("fighters") == []


def test_folding_loose_files_preserves_text_and_can_leave_them_in_place(tmp_path):
    (tmp_path / "events").mkdir()
    with gzip.open(tmp_path / "events" / "4088.html.gz", "wt", encoding="utf-8") as fh:
        fh.write(PAGE)
    (tmp_path / "profiles.html").write_text(PAGE, encoding="utf-8")

    folded = fold_in_loose_files(
        tmp_path, {"events": (".html.gz",), ".": (".html",)}, remove=False
    )

    cache = open_cache(tmp_path)
    assert folded == {"events": 1, ".": 1}
    assert cache.get("events", "4088") == PAGE
    assert cache.get(".", "profiles") == PAGE
    assert (tmp_path / "events" / "4088.html.gz").exists(), "remove=False keeps the original"


def test_folding_twice_does_not_refetch_or_overwrite(tmp_path):
    (tmp_path / "events").mkdir()
    with gzip.open(tmp_path / "events" / "1.html.gz", "wt", encoding="utf-8") as fh:
        fh.write("from disk")
    fold_in_loose_files(tmp_path, {"events": (".html.gz",)}, remove=False)
    open_cache(tmp_path).put("events", "1", "corrected after the fold")

    again = fold_in_loose_files(tmp_path, {"events": (".html.gz",)}, remove=True)

    assert again == {"events": 0}
    assert open_cache(tmp_path).get("events", "1") == "corrected after the fold"
    assert not (tmp_path / "events" / "1.html.gz").exists()


def test_a_missing_cache_directory_folds_to_nothing_rather_than_raising(tmp_path):
    assert fold_in_loose_files(tmp_path, {"events": (".html.gz",)}) == {}


def test_a_store_survives_being_closed_and_reopened(tmp_path):
    with PageCache(tmp_path / STORE_NAME) as cache:
        cache.put("events", "1", PAGE)
    with PageCache(tmp_path / STORE_NAME) as reopened:
        assert reopened.get("events", "1") == PAGE


@pytest.mark.parametrize("length", [0, 500_000], ids=["empty", "large"])
def test_empty_and_large_pages_round_trip(tmp_path, length):
    text = "x" * length
    cache = open_cache(tmp_path)
    cache.put("fighters", "1", text)
    assert cache.get("fighters", "1") == text
