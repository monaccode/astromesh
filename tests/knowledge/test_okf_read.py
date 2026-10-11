"""Bundle.read: payload, normalización de IDs, links resueltos y confinamiento."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import (
    Bundle,
    BundleError,
    ConceptNotFoundError,
    InvalidConceptError,
    NotAConceptError,
    OutsideBundleError,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)
B = Bundle(FIX)


def test_read_payload():
    r = B.read("tables/orders", now=NOW)
    assert set(r) == {
        "id",
        "type",
        "title",
        "description",
        "tags",
        "status",
        "trust",
        "stale",
        "warnings",
        "extra",
        "body",
        "links",
    }
    assert r["id"] == "tables/orders"
    assert r["trust"] == "human-reviewed"
    assert r["warnings"] == []
    assert r["extra"]["resource"].startswith("https://console.cloud.google.com/")
    assert r["body"].startswith("# Schema")


@pytest.mark.parametrize(
    "raw",
    ["tables/orders", "/tables/orders.md", "./tables/orders.md", "tables/orders.md#schema"],
)
def test_ids_are_normalized(raw):
    assert B.read(raw)["id"] == "tables/orders"


def test_links_are_resolved_to_concept_ids():
    assert B.read("tables/orders")["links"] == [
        {"id": "metrics/revenue", "exists": True},
        {"id": "metrics/gross-margin", "exists": True},
        {"id": "metrics", "dir": True, "exists": True},
        {"id": "tables/customers", "exists": False},
        {"url": "https://example.com/orders", "external": True},
        {"id": "tables", "dir": True, "exists": True},
    ]


def test_relative_link_with_dot():
    assert B.read("metrics/gross-margin-legacy")["links"] == [
        {"id": "metrics/gross-margin", "exists": True}
    ]


def test_missing_concept_suggests_close_ids():
    with pytest.raises(ConceptNotFoundError) as exc:
        B.read("metrics/revenu")
    assert str(exc.value).startswith("concept not found: metrics/revenu (did you mean: ")
    assert "metrics/revenue" in str(exc.value)


def test_missing_concept_without_suggestions():
    with pytest.raises(ConceptNotFoundError, match=r"^concept not found: zzz/qqq$"):
        B.read("zzz/qqq")


def test_python_file_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: attesters/check.py$"):
        B.read("attesters/check.py")


def test_reserved_file_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: metrics/log$"):
        B.read("metrics/log")


def test_directory_is_not_a_concept():
    with pytest.raises(NotAConceptError, match=r"^not a concept: metrics$"):
        B.read("metrics")


def test_invalid_concept_is_reported():
    with pytest.raises(InvalidConceptError, match=r"^invalid concept metrics/broken: "):
        B.read("metrics/broken")


@pytest.mark.parametrize("raw", ["../outside", "/../../etc/passwd", "metrics/../../x"])
def test_traversal_is_blocked(raw):
    with pytest.raises(OutsideBundleError, match=r"^outside bundle: "):
        B.read(raw)


def test_absolute_path_never_reads_outside(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("---\ntype: X\n---\nSECRET")
    with pytest.raises(BundleError):
        B.read(str(secret))


def test_symlink_escaping_the_bundle_is_blocked(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    (root / "ok.md").write_text("---\ntype: X\n---\nok")
    secret = tmp_path / "secret.md"
    secret.write_text("---\ntype: X\n---\nSECRET")
    (root / "leak.md").symlink_to(secret)
    b = Bundle(root)
    assert b.read("ok")["body"] == "ok"
    with pytest.raises(OutsideBundleError):
        b.read("leak")
    with pytest.raises(OutsideBundleError):
        b.read("leak.md")
