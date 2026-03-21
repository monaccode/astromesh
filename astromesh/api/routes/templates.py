import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter()
_templates_dir: str | None = None


def set_templates_dir(path: str | None) -> None:
    """Override template directory (tests). None = use auto-discovery."""
    global _templates_dir
    _templates_dir = path


def _resolve_default_templates_dir() -> Path | None:
    """Find bundled / repo templates without an explicit set_templates_dir call."""
    env = os.environ.get("ASTROMESH_TEMPLATES_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    cwd_candidate = (Path.cwd() / "config" / "templates").resolve()
    if cwd_candidate.is_dir():
        return cwd_candidate
    try:
        import astromesh

        pkg_anchor = Path(astromesh.__file__).resolve().parent.parent
        dev_candidate = (pkg_anchor / "config" / "templates").resolve()
        if dev_candidate.is_dir():
            return dev_candidate
    except Exception:
        pass
    return None


def _active_templates_dir() -> Path | None:
    if _templates_dir is not None:
        p = Path(_templates_dir)
        return p if p.is_dir() else None
    return _resolve_default_templates_dir()


def _load_templates() -> list[dict]:
    tpl_path = _active_templates_dir()
    if not tpl_path:
        return []
    templates = []
    for f in sorted(tpl_path.glob("*.template.yaml")):
        with open(f) as fh:
            templates.append(yaml.safe_load(fh))
    return templates


@router.get("/templates")
async def list_templates():
    templates = _load_templates()
    return [
        {
            "name": t["metadata"]["name"],
            "version": t["metadata"].get("version", ""),
            "category": t["metadata"].get("category", ""),
            "tags": t["metadata"].get("tags", []),
            "display_name": t["template"]["display_name"],
            "description": t["template"]["description"],
            "recommended_channels": t["template"].get("recommended_channels", []),
        }
        for t in templates
    ]


@router.get("/templates/{template_name}")
async def get_template(template_name: str):
    templates = _load_templates()
    for t in templates:
        if t["metadata"]["name"] == template_name:
            return {
                "name": t["metadata"]["name"],
                "version": t["metadata"].get("version", ""),
                "category": t["metadata"].get("category", ""),
                "tags": t["metadata"].get("tags", []),
                "display_name": t["template"]["display_name"],
                "description": t["template"]["description"],
                "recommended_channels": t["template"].get("recommended_channels", []),
                "variables": t["template"].get("variables", []),
                "agent_config": t["template"]["agent_config"],
            }
    raise HTTPException(404, f"Template '{template_name}' not found")
