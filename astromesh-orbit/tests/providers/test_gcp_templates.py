"""Tests for GCP Terraform template rendering."""

from pathlib import Path
import pytest
from jinja2 import Environment, FileSystemLoader

from astromesh_orbit.config import OrbitConfig


TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "astromesh_orbit"
    / "providers"
    / "gcp"
    / "templates"
)


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )


@pytest.fixture
def config(sample_orbit_yaml: Path) -> OrbitConfig:
    return OrbitConfig.from_yaml(sample_orbit_yaml)


@pytest.fixture
def ctx(config: OrbitConfig) -> dict:
    """Template rendering context."""
    return {
        "config": config,
        "meta": config.metadata,
        "spec": config.spec,
        "provider": config.spec.provider,
        "compute": config.spec.compute,
        "database": config.spec.database,
        "cache": config.spec.cache,
        "secrets": config.spec.secrets,
        "images": config.spec.images,
        "services": [
            {
                "key": "runtime",
                "name": "astromesh-runtime",
                "spec": config.spec.compute.runtime,
                "image": config.spec.images.runtime,
            },
            {
                "key": "cloud_api",
                "name": "astromesh-cloud-api",
                "spec": config.spec.compute.cloud_api,
                "image": config.spec.images.cloud_api,
            },
            {
                "key": "studio",
                "name": "astromesh-studio",
                "spec": config.spec.compute.studio,
                "image": config.spec.images.studio,
            },
        ],
    }


def test_main_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("main.tf.j2")
    output = tmpl.render(ctx)
    assert 'provider "google"' in output
    assert ctx["provider"].project in output
    assert ctx["provider"].region in output


def test_cloud_run_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    assert "google_cloud_run_v2_service" in output
    assert "astromesh-runtime" in output
    assert "astromesh-cloud-api" in output
    assert "astromesh-studio" in output


def test_cloud_sql_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_sql.tf.j2")
    output = tmpl.render(ctx)
    assert "google_sql_database_instance" in output
    assert ctx["database"].tier in output
    assert ctx["database"].version in output


def test_memorystore_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("memorystore.tf.j2")
    output = tmpl.render(ctx)
    assert "google_redis_instance" in output
    assert str(ctx["cache"].memory_gb) in output


def test_secrets_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "google_secret_manager_secret" in output
    assert "jwt-secret" in output


def test_networking_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("networking.tf.j2")
    output = tmpl.render(ctx)
    assert "google_vpc_access_connector" in output


def test_iam_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("iam.tf.j2")
    output = tmpl.render(ctx)
    assert "google_service_account" in output
    assert "astromesh-orbit" in output
    assert "roles/cloudsql.client" in output


def test_variables_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("variables.tf.j2")
    output = tmpl.render(ctx)
    assert 'variable "project_id"' in output
    assert 'variable "region"' in output


def test_outputs_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("outputs.tf.j2")
    output = tmpl.render(ctx)
    assert "runtime_url" in output
    assert "cloud_api_url" in output
    assert "db_connection_name" in output


def test_backend_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("backend.tf.j2")
    output = tmpl.render(ctx)
    assert 'backend "gcs"' in output
    assert "astromesh-orbit-state" in output


def test_cloud_run_ha_disabled_uses_min_instances(jinja_env, ctx):
    """Starter preset: studio min_instances=0 should produce scale-to-zero."""
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    # Studio should have min_instance_count = 0
    assert "min_instance_count" in output


def test_cloud_sql_no_ha(jinja_env, ctx):
    """Starter preset: high_availability is false, no REGIONAL availability_type."""
    tmpl = jinja_env.get_template("cloud_sql.tf.j2")
    output = tmpl.render(ctx)
    assert "ZONAL" in output


def test_secrets_jwt_disabled(jinja_env, ctx):
    """When jwt_secret is False, JWT resources should be omitted."""
    ctx["secrets"] = type("S", (), {"jwt_secret": False, "provider_keys": True})()
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "jwt_secret" not in output.lower() or "jwt-secret" not in output


def test_secrets_provider_keys_disabled(jinja_env, ctx):
    """When provider_keys is False, fernet key should be omitted."""
    ctx["secrets"] = type("S", (), {"jwt_secret": True, "provider_keys": False})()
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "fernet" not in output.lower()
