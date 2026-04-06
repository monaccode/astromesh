"""GCP provider — generates Terraform for Google Cloud."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.core.provider import (
    DeploymentStatus,
    ProvisionResult,
    ResourceStatus,
    ValidationResult,
)
from astromesh_orbit.providers.gcp.validators import (
    check_apis_enabled,
    check_gcloud_auth,
    check_project,
)
from astromesh_orbit.terraform.backend import ensure_gcs_state_bucket
from astromesh_orbit.terraform.runner import TerraformRunner

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Templates to render in order
TEMPLATE_FILES = [
    "main.tf.j2",
    "variables.tf.j2",
    "backend.tf.j2",
    "iam.tf.j2",
    "networking.tf.j2",
    "cloud_sql.tf.j2",
    "memorystore.tf.j2",
    "secrets.tf.j2",
    "cloud_run.tf.j2",
    "outputs.tf.j2",
]


class GCPProvider:
    name: str = "gcp"

    def __init__(self) -> None:
        self._jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            keep_trailing_newline=True,
        )
        self._tf = TerraformRunner()

    def _build_context(self, config: OrbitConfig) -> dict:
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
            ],
        }

    async def validate(self, config: OrbitConfig) -> ValidationResult:
        project = config.spec.provider.project
        checks = [await check_gcloud_auth(), await check_project(project)]
        checks.extend(await check_apis_enabled(project))
        ok = all(c.passed for c in checks)
        return ValidationResult(ok=ok, checks=checks)

    async def generate(self, config: OrbitConfig, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._build_context(config)
        generated = []
        for tmpl_name in TEMPLATE_FILES:
            tmpl = self._jinja.get_template(tmpl_name)
            out_name = tmpl_name.replace(".j2", "")
            out_path = output_dir / out_name
            out_path.write_text(tmpl.render(ctx))
            generated.append(out_path)
        return generated

    async def provision(self, config: OrbitConfig, output_dir: Path) -> ProvisionResult:
        # Validate first
        validation = await self.validate(config)
        if not validation.ok:
            failed = [c for c in validation.checks if not c.passed]
            msgs = "\n".join(
                f"  - {c.message}" + (f" -> {c.remediation}" if c.remediation else "")
                for c in failed
            )
            raise RuntimeError(f"Validation failed:\n{msgs}")

        # Ensure state bucket
        await ensure_gcs_state_bucket(
            config.spec.provider.project,
            config.spec.provider.region,
            config.metadata.name,
        )

        # Generate and apply
        work_dir = output_dir
        await self.generate(config, work_dir)
        await self._tf.init(work_dir)
        result = await self._tf.apply(work_dir, auto_approve=True)

        if not result.success:
            raise RuntimeError(f"terraform apply failed:\n{result.raw_output}")

        # Write orbit.env
        env_path = output_dir.parent / "orbit.env"
        env_lines = [f"{k.upper()}={v}" for k, v in result.outputs.items()]
        env_path.write_text("\n".join(env_lines) + "\n")

        endpoints = {
            "runtime": result.outputs.get("runtime_url", ""),
        }

        return ProvisionResult(apply=result, env_file=env_path, endpoints=endpoints)

    async def status(self, config: OrbitConfig) -> DeploymentStatus:
        outputs = await self._tf.output(Path(".orbit/generated"))
        resources = []
        for key in ["runtime"]:
            url_key = f"{key}_url"
            url = outputs.get(url_key)
            resources.append(
                ResourceStatus(
                    name=f"astromesh-{key.replace('_', '-')}",
                    resource_type="cloud_run_v2_service",
                    status="running" if url else "not_found",
                    url=url,
                )
            )
        return DeploymentStatus(
            resources=resources,
            state_bucket=f"{config.spec.provider.project}-astromesh-orbit-state",
            last_applied=None,
        )

    async def destroy(self, config: OrbitConfig, output_dir: Path) -> None:
        await self._tf.destroy(output_dir, auto_approve=True)

    async def eject(self, config: OrbitConfig, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._build_context(config)
        for tmpl_name in TEMPLATE_FILES:
            tmpl = self._jinja.get_template(tmpl_name)
            out_name = tmpl_name.replace(".j2", "")
            content = tmpl.render(ctx)
            # Add explanatory header comment
            comment = (
                f"# {out_name} -- Generated by Astromesh Orbit (ejected)\n"
                f"# Safe to modify. No Orbit dependency.\n\n"
            )
            (output_dir / out_name).write_text(comment + content)

        # Write terraform.tfvars with resolved values from orbit.yaml
        tfvars_lines = [
            f'project_id      = "{config.spec.provider.project}"',
            f'region          = "{config.spec.provider.region}"',
            f'deployment_name = "{config.metadata.name}"',
        ]
        (output_dir / "terraform.tfvars").write_text("\n".join(tfvars_lines) + "\n")

        return output_dir
