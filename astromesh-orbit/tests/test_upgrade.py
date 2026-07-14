"""orbit upgrade — diffing freshly-rendered templates against the generated ones."""

from pathlib import Path

from astromesh_orbit.upgrade import apply_generated, diff_generated, stale_tf_files


def test_no_diff_when_identical(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (new / "main.tf").write_text('provider "google" {}\n')
    (current / "main.tf").write_text('provider "google" {}\n')
    assert diff_generated(new, current) == ""


def test_diff_shows_changed_lines(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (current / "main.tf").write_text('region = "us-central1"\n')
    (new / "main.tf").write_text('region = "europe-west1"\n')
    diff = diff_generated(new, current)
    assert '-region = "us-central1"' in diff
    assert '+region = "europe-west1"' in diff


def test_new_file_shows_as_additions(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (new / "monitoring.tf").write_text('resource "google_monitoring_dashboard" "main" {}\n')
    diff = diff_generated(new, current)
    assert '+resource "google_monitoring_dashboard" "main" {}' in diff


def test_only_tf_files_are_compared(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (new / "notes.txt").write_text("ignore me\n")
    assert diff_generated(new, current) == ""


def test_removed_file_shows_as_deletion(tmp_path: Path):
    # A .tf that current has but the new render no longer produces must show as all-deletions,
    # otherwise `orbit upgrade` silently hides a dropped resource.
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (current / "legacy.tf").write_text('resource "google_thing" "old" {}\n')
    diff = diff_generated(new, current)
    assert "legacy.tf" in diff
    assert '-resource "google_thing" "old" {}' in diff


def test_stale_tf_files_lists_removed(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (new / "main.tf").write_text("keep\n")
    (current / "main.tf").write_text("keep\n")
    (current / "legacy.tf").write_text("drop\n")
    stale = stale_tf_files(new, current)
    assert [p.name for p in stale] == ["legacy.tf"]


def test_stale_tf_files_empty_when_current_is_subset(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (new / "main.tf").write_text("x\n")
    (new / "extra.tf").write_text("y\n")
    (current / "main.tf").write_text("x\n")
    assert stale_tf_files(new, current) == []


def test_apply_removes_stale_and_copies_new(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"
    new.mkdir()
    current.mkdir()
    (current / "main.tf").write_text("old main\n")
    (current / "legacy.tf").write_text("dropped\n")
    (new / "main.tf").write_text("new main\n")
    (new / "monitoring.tf").write_text("added\n")

    apply_generated(new, current)

    assert (current / "main.tf").read_text() == "new main\n"  # overwritten
    assert (current / "monitoring.tf").read_text() == "added\n"  # copied in
    assert not (current / "legacy.tf").exists()  # stale removed
    assert sorted(p.name for p in current.glob("*.tf")) == ["main.tf", "monitoring.tf"]


def test_apply_creates_current_dir_if_missing(tmp_path: Path):
    new = tmp_path / "new"
    current = tmp_path / "current"  # does not exist yet
    new.mkdir()
    (new / "main.tf").write_text("hello\n")

    apply_generated(new, current)

    assert (current / "main.tf").read_text() == "hello\n"
