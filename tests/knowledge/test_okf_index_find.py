"""Bundle.index (existente y sintetizado, §8) y Bundle.find."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import Bundle, BundleError, OutsideBundleError

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)
B = Bundle(FIX)


def _ids(result):
    return [row["id"] for row in result["results"]]


def test_root_index_is_returned_without_frontmatter():
    out = B.index("/")
    assert out.startswith("# Subdirectories")
    assert "okf_version" not in out


def test_existing_subdirectory_index_is_returned_as_is():
    assert B.index("tables") == "# Tables\n\n* [Orders](orders.md) - One row per completed order.\n"


def test_missing_index_is_synthesized():
    assert B.index("metrics", now=NOW) == (
        "# Concepts\n"
        "\n"
        "* [Churn](metrics/churn) - Share of customers lost in a period. [metric, draft]\n"
        "* [Gross Margin](metrics/gross-margin) - Revenue minus cost of goods. [Metric, stale]\n"
        "* [Gross Margin (legacy)](metrics/gross-margin-legacy) - Retired definition."
        " [Metric, deprecated]\n"
        "* [legacy-v01](metrics/legacy-v01) [Reference]\n"
        "* [Revenue](metrics/revenue) - Recognized revenue for a fiscal year. [Metric]\n"
        "\n"
        "(2 concept(s) skipped: invalid frontmatter)\n"
    )


def test_synthesized_index_lists_subdirectories(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text("---\ntype: X\n---\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "top.md").write_text("---\ntype: X\ntitle: Top\n---\n")
    assert Bundle(tmp_path).index("/") == (
        "# Subdirectories\n\n* [a](a/)\n\n# Concepts\n\n* [Top](top) [X]\n"
    )


def test_empty_directory(tmp_path):
    (tmp_path / "empty").mkdir()
    assert Bundle(tmp_path).index("empty") == "(empty directory)\n"


def test_index_of_a_file_is_an_error():
    with pytest.raises(BundleError, match=r"^not a directory: metrics/revenue$"):
        B.index("metrics/revenue")


def test_index_outside_bundle_is_blocked():
    with pytest.raises(OutsideBundleError):
        B.index("../")


def test_synthesized_index_logs_skipped(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.knowledge.okf"):
        B.index("metrics")
    assert "omitido" in caplog.text


def test_find_without_filters_excludes_deprecated_and_counts_invalid():
    r = B.find(now=NOW)
    assert _ids(r) == [
        "metrics/churn",
        "metrics/gross-margin",
        "metrics/legacy-v01",
        "metrics/revenue",
        "tables/orders",
    ]
    assert r["skipped_invalid"] == 2


def test_find_include_deprecated():
    assert "metrics/gross-margin-legacy" in _ids(B.find(include_deprecated=True))


def test_find_by_type_is_case_insensitive():
    assert _ids(B.find(type_="Metric")) == [
        "metrics/churn",
        "metrics/gross-margin",
        "metrics/revenue",
    ]


def test_find_by_tags_requires_all_case_insensitive():
    assert _ids(B.find(tags=["finance"])) == ["metrics/gross-margin", "metrics/revenue"]
    assert _ids(B.find(tags=["FINANCE", "margin"])) == ["metrics/gross-margin"]


def test_find_text_ranks_header_matches_before_body_matches():
    assert _ids(B.find(text="REVENUE")) == [
        "metrics/gross-margin",
        "metrics/revenue",
        "metrics/churn",
        "tables/orders",
    ]


def test_find_rows_have_summary_keys_only():
    row = B.find(text="orders")["results"][0]
    assert set(row) == {"id", "type", "title", "description", "status", "trust", "stale"}


def test_find_limit_is_clamped():
    assert len(B.find(limit=2)["results"]) == 2
    assert len(B.find(limit=0)["results"]) == 1
    assert len(B.find(limit=10_000)["results"]) == 5


def test_find_skips_hidden_dirs_and_escaping_symlinks(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    (root / "ok.md").write_text("---\ntype: X\n---\n")
    (root / ".git").mkdir()
    (root / ".git" / "hidden.md").write_text("---\ntype: X\n---\n")
    outside = tmp_path / "outdir"
    outside.mkdir()
    (outside / "leak.md").write_text("---\ntype: X\n---\nSECRET")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "leak.md").symlink_to(outside / "leak.md")
    assert _ids(Bundle(root).find()) == ["ok"]


def test_directory_named_md_is_not_a_concept(tmp_path):
    (tmp_path / "x.md").mkdir()
    (tmp_path / "valid.md").write_text("---\ntype: X\ntitle: Valid\n---\n")
    b = Bundle(tmp_path)
    result = b.index("/")
    assert "Valid" in result
    assert "concept(s) skipped" not in result


def test_index_md_non_utf8_raises_bundle_error(tmp_path):
    (tmp_path / "index.md").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(BundleError, match=r"^invalid index: /$"):
        Bundle(tmp_path).index("/")
