"""Parseo de conceptos OKF v0.2: campos, señales de confianza y tolerancia (§11)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astromesh.knowledge.okf import InvalidConceptError, parse_concept

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"
NOW = datetime(2026, 10, 11, tzinfo=UTC)


def _c(rel):
    return parse_concept(FIX, FIX / rel, now=NOW)


def _tmp(tmp_path, text, name="x.md"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return parse_concept(tmp_path, path, now=NOW)


def test_basic_fields():
    c = _c("tables/orders.md")
    assert c.id == "tables/orders"
    assert c.type == "BigQuery Table"
    assert c.title == "Orders"
    assert c.description == "One row per completed order."
    assert c.tags == ["sales", "orders"]
    assert c.status == "stable"
    assert c.body.startswith("# Schema")


def test_verified_as_bare_mapping_with_human_is_human_reviewed():
    assert _c("tables/orders.md").trust == "human-reviewed"


def test_verified_by_process_only_is_machine_confirmed():
    assert _c("metrics/revenue.md").trust == "machine-confirmed"


def test_no_verified_is_unverified():
    assert _c("metrics/churn.md").trust == "unverified"


def test_past_stale_after_is_stale_and_warns():
    c = _c("metrics/gross-margin.md")
    assert c.stale is True
    assert c.warnings == ["STALE since 2020-01-01T00:00:00+00:00: may no longer be accurate."]


def test_future_stale_after_is_not_stale():
    c = _c("metrics/revenue.md")
    assert c.stale is False
    assert c.warnings == []


def test_deprecated_warns():
    c = _c("metrics/gross-margin-legacy.md")
    assert c.status == "deprecated"
    assert c.warnings == ["DEPRECATED: kept for history; do not use for new work."]


def test_draft_warns():
    assert _c("metrics/churn.md").warnings == ["DRAFT: not reviewed; may be incomplete."]


def test_warnings_order_deprecated_stale_draft(tmp_path):
    c = _tmp(tmp_path, "---\ntype: X\nstatus: deprecated\nstale_after: 2020-01-01\n---\nb")
    assert [w.split(":")[0] for w in c.warnings] == ["DEPRECATED", "STALE since 2020-01-01T00"]


def test_unknown_keys_are_preserved_in_extra():
    c = _c("metrics/revenue.md")
    assert c.extra["owner"] == "finance"
    assert c.extra["resource"] == "https://wiki.acme/finance/revenue"
    assert c.extra["sources"][0]["id"] == "rev-policy"
    assert "type" not in c.extra
    assert "title" not in c.extra


def test_extra_is_json_serializable():
    c = _c("metrics/revenue.md")
    assert json.loads(json.dumps(c.extra))["generated"]["at"] == "2026-06-20T22:53:05+00:00"


def test_generated_at_comes_from_generated():
    assert _c("metrics/revenue.md").generated_at == "2026-06-20T22:53:05+00:00"


def test_v01_timestamp_fallback_and_title_from_filename():
    c = _c("metrics/legacy-v01.md")
    assert c.generated_at == "2026-05-28T22:53:05+00:00"
    assert c.title == "legacy-v01"


def test_summary_keys():
    assert set(_c("metrics/revenue.md").summary()) == {
        "id",
        "type",
        "title",
        "description",
        "status",
        "trust",
        "stale",
    }


def test_unparseable_frontmatter_is_invalid():
    with pytest.raises(InvalidConceptError, match=r"^invalid concept metrics/broken: "):
        _c("metrics/broken.md")


def test_missing_type_is_invalid():
    with pytest.raises(
        InvalidConceptError, match=r"^invalid concept metrics/no-type: missing type$"
    ):
        _c("metrics/no-type.md")


def test_no_frontmatter_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="missing frontmatter"):
        _tmp(tmp_path, "# Just markdown\n")


def test_frontmatter_that_is_not_a_mapping_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="not a mapping"):
        _tmp(tmp_path, "---\n- a\n- b\n---\nbody")


def test_unterminated_frontmatter_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="unterminated"):
        _tmp(tmp_path, "---\ntype: X\n")


def test_non_utf8_is_invalid(tmp_path):
    with pytest.raises(InvalidConceptError, match="not UTF-8"):
        _tmp(tmp_path, b"---\ntype: X\n---\n\xff\xfe")


def test_crlf_and_bom_parse(tmp_path):
    c = _tmp(tmp_path, "﻿---\r\ntype: X\r\ntitle: T\r\n---\r\nbody\r\n")
    assert (c.type, c.title, c.body) == ("X", "T", "body")


def test_tags_as_string_become_a_list(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\ntags: finance\n---\n").tags == ["finance"]


def test_non_string_title_is_stringified(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\ntitle: 2026\n---\n").title == "2026"


def test_stale_after_as_quoted_string(tmp_path):
    assert _tmp(tmp_path, '---\ntype: X\nstale_after: "2020-01-01T00:00:00Z"\n---\n').stale


def test_stale_after_as_date_only(tmp_path):
    assert _tmp(tmp_path, "---\ntype: X\nstale_after: 2020-01-01\n---\n").stale


def test_unreadable_stale_after_is_ignored_and_logged(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.knowledge.okf"):
        c = _tmp(tmp_path, "---\ntype: X\nstale_after: next tuesday\n---\n")
    assert c.stale is False
    assert c.warnings == []
    assert "stale_after" in caplog.text
