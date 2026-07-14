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
        "storage": config.spec.storage,
        "observability": config.spec.observability,
        "custom_env": {},
        "services": [
            {
                "key": "runtime",
                "name": "astromesh-runtime",
                "spec": config.spec.compute.runtime,
                "image": config.spec.images.runtime,
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
    assert "db_connection_name" in output


def test_backend_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("backend.tf.j2")
    output = tmpl.render(ctx)
    assert 'backend "gcs"' in output
    assert "astromesh-orbit-state" in output


def test_cloud_run_renders_min_instances(jinja_env, ctx):
    """Runtime should render min_instance_count."""
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
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


def test_storage_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("storage.tf.j2")
    output = tmpl.render(ctx)
    assert "google_storage_bucket" in output
    assert "rag-docs" in output
    assert "roles/storage.objectAdmin" in output
    assert "uniform_bucket_level_access = true" in output


def test_storage_tf_disabled(jinja_env, ctx):
    from astromesh_orbit.config import RagDocumentsSpec, StorageSpec

    ctx["storage"] = StorageSpec(rag_documents=RagDocumentsSpec(enabled=False))
    tmpl = jinja_env.get_template("storage.tf.j2")
    output = tmpl.render(ctx)
    assert "google_storage_bucket" not in output


def test_artifact_registry_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("artifact_registry.tf.j2")
    output = tmpl.render(ctx)
    assert "google_artifact_registry_repository" in output
    assert '"DOCKER"' in output
    assert "roles/artifactregistry.reader" in output


def test_artifact_registry_default_repo_name(jinja_env, ctx):
    # meta.name == "test-astromesh" -> default repository "test-astromesh-images"
    tmpl = jinja_env.get_template("artifact_registry.tf.j2")
    output = tmpl.render(ctx)
    assert "test-astromesh-images" in output


def test_artifact_registry_disabled(jinja_env, ctx):
    from astromesh_orbit.config import ArtifactRegistrySpec, StorageSpec

    ctx["storage"] = StorageSpec(artifact_registry=ArtifactRegistrySpec(enabled=False))
    tmpl = jinja_env.get_template("artifact_registry.tf.j2")
    output = tmpl.render(ctx)
    assert "google_artifact_registry_repository" not in output


def test_cloud_run_includes_rag_bucket_env(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    assert "ASTROMESH_RAG_BUCKET" in output


def test_cloud_run_omits_rag_bucket_when_disabled(jinja_env, ctx):
    from astromesh_orbit.config import RagDocumentsSpec, StorageSpec

    ctx["storage"] = StorageSpec(rag_documents=RagDocumentsSpec(enabled=False))
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    assert "ASTROMESH_RAG_BUCKET" not in output


def test_outputs_include_storage(jinja_env, ctx):
    tmpl = jinja_env.get_template("outputs.tf.j2")
    output = tmpl.render(ctx)
    assert "rag_bucket" in output
    assert "artifact_registry_repo" in output


def test_monitoring_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("monitoring.tf.j2")
    output = tmpl.render(ctx)
    assert "google_monitoring_dashboard" in output
    assert "run.googleapis.com/request_count" in output
    assert "run.googleapis.com/request_latencies" in output
    assert "astromesh-runtime" in output


def test_monitoring_tf_disabled(jinja_env, ctx):
    from astromesh_orbit.config import ObservabilitySpec

    ctx["observability"] = ObservabilitySpec(dashboard=False)
    tmpl = jinja_env.get_template("monitoring.tf.j2")
    output = tmpl.render(ctx)
    assert "google_monitoring_dashboard" not in output


def _tracing_ctx(ctx):
    """ctx with tracing enabled (dashboard left at its default)."""
    from astromesh_orbit.config import ObservabilitySpec, TracingSpec

    ctx["observability"] = ObservabilitySpec(tracing=TracingSpec(enabled=True))
    return ctx


def test_cloud_run_renders_collector_sidecar(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(_tracing_ctx(ctx))
    assert "otel-collector" in output
    assert "--config=env:OTEL_COLLECTOR_CONFIG" in output
    assert "googlecloud" in output
    assert "0.0.0.0:4317" in output


def test_cloud_run_renders_otlp_env_when_tracing(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(_tracing_ctx(ctx))
    assert "ASTROMESH_OTLP_ENABLED" in output
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in output
    assert "http://localhost:4317" in output
    assert 'depends_on = ["otel-collector"]' in output


def test_cloud_run_omits_tracing_when_disabled(jinja_env, ctx):
    # ctx's default observability has tracing.enabled = False
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    assert "otel-collector" not in output
    assert "ASTROMESH_OTLP_ENABLED" not in output
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in output
