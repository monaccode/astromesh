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


def _bundled_templates_root() -> Path | None:
    """Templates shipped with the installed package (wheel) or the source repo (dev)."""
    try:
        import astromesh

        pkg_dir = Path(astromesh.__file__).resolve().parent
        # Wheel layout: config/ force-included under the package as _bundled/config
        wheel_path = pkg_dir / "_bundled" / "config" / "templates"
        if wheel_path.is_dir():
            return wheel_path
        # Dev/source layout: repo_root/config/templates
        repo_path = pkg_dir.parent / "config" / "templates"
        if repo_path.is_dir():
            return repo_path
        return None
    except Exception:
        return None


def _iter_template_root_dirs() -> list[Path]:
    """Directories to scan for `*.template.yaml`, in merge order (later overrides name)."""
    if _templates_dir is not None:
        p = Path(_templates_dir)
        return [p.resolve()] if p.is_dir() else []

    seen: set[Path] = set()
    roots: list[Path] = []

    def add(path: Path | None) -> None:
        if path is None or not path.is_dir():
            return
        r = path.resolve()
        if r in seen:
            return
        seen.add(r)
        roots.append(r)

    add(_bundled_templates_root())
    cfg = os.environ.get("ASTROMESH_CONFIG_DIR", "").strip()
    if cfg:
        add(Path(cfg).expanduser().resolve() / "templates")
    add((Path.cwd() / "config" / "templates").resolve())
    env = os.environ.get("ASTROMESH_TEMPLATES_DIR", "").strip()
    if env:
        add(Path(env).expanduser().resolve())
    return roots


def _load_templates() -> list[dict]:
    by_name: dict[str, dict] = {}
    for root in _iter_template_root_dirs():
        for f in sorted(root.glob("*.template.yaml")):
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue
            meta = data.get("metadata") or {}
            tname = meta.get("name")
            if not tname:
                continue
            by_name[str(tname)] = data
    return list(by_name.values())


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
