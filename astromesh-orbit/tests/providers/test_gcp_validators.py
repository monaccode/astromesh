"""Tests for GCP validator constants."""

from astromesh_orbit.providers.gcp.validators import REQUIRED_APIS


def test_storage_and_artifact_registry_apis_required():
    assert "storage.googleapis.com" in REQUIRED_APIS
    assert "artifactregistry.googleapis.com" in REQUIRED_APIS
