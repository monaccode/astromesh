# astromesh/workflow/loader.py
from __future__ import annotations

from pathlib import Path

import yaml

from astromesh.workflow.models import RetryConfig, StepSpec, WorkflowSpec


class WorkflowLoader:
    """Loads *.workflow.yaml files from a directory into WorkflowSpec instances."""

    def __init__(self, workflows_dir: str):
        self._dir = Path(workflows_dir)

    def load_all(self) -> dict[str, WorkflowSpec]:
        """Load all workflow YAML files from the directory. Returns {name: WorkflowSpec}."""
        if not self._dir.exists():
            return {}
        workflows: dict[str, WorkflowSpec] = {}
        for f in self._dir.glob("*.workflow.yaml"):
            try:
                wf = self.load_file(f)
                workflows[wf.name] = wf
            except Exception:
                continue  # skip invalid files
        return workflows

    def load_file(self, path: Path) -> WorkflowSpec:
        """Load a single workflow YAML file."""
        raw = yaml.safe_load(path.read_text())
        if raw.get("kind") != "Workflow":
            raise ValueError(f"Expected kind: Workflow, got: {raw.get('kind')}")
        return self._parse(raw)

    def _parse(self, raw: dict) -> WorkflowSpec:
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})
        steps = []
        for step_raw in spec.get("steps", []):
            steps.append(self._parse_step(step_raw))
        return WorkflowSpec(
            name=metadata["name"],
            version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("description", ""),
            trigger=spec.get("trigger", "api"),
            timeout_seconds=spec.get("timeout_seconds", 300),
            steps=steps,
            observability=spec.get("observability", {}),
        )

    def _parse_step(self, raw: dict) -> StepSpec:
        retry_raw = raw.get("retry")
        retry = RetryConfig(**retry_raw) if retry_raw else None
        return StepSpec(
            name=raw["name"],
            agent=raw.get("agent"),
            tool=raw.get("tool"),
            switch=raw.get("switch"),
            input_template=raw.get("input"),
            arguments=raw.get("arguments"),
            context_transform=raw.get("context_transform"),
            retry=retry,
            timeout_seconds=raw.get("timeout_seconds"),
            on_error=raw.get("on_error"),
        )
