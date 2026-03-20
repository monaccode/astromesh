from fastapi import APIRouter, HTTPException
from pathlib import Path
import yaml

router = APIRouter()
_templates_dir: str | None = None


def set_templates_dir(path: str) -> None:
    global _templates_dir
    _templates_dir = path


def _load_templates() -> list[dict]:
    if not _templates_dir:
        return []
    tpl_path = Path(_templates_dir)
    if not tpl_path.exists():
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
