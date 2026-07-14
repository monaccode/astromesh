"""orbit upgrade — diffing freshly-rendered templates against the generated ones."""

from pathlib import Path

from astromesh_orbit.upgrade import diff_generated


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
