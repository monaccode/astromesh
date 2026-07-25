"""Catálogo de integraciones declarativas."""

from __future__ import annotations

import logging
from pathlib import Path

from astromesh.integrations.handlers import HandlerError, load_handler
from astromesh.integrations.manifest import IntegrationManifest, ManifestError, load_manifest

logger = logging.getLogger(__name__)

_CATALOG_ROOT = Path(__file__).parent / "catalog"


class IntegrationCatalog:
    """Descubre, valida y cachea los manifests de `catalog/`."""

    def __init__(self):
        self._manifests: dict[str, IntegrationManifest] = {}

    def discover(self, root: Path | None = None) -> int:
        """Escanea `<root>/*/integration.yaml`. Devuelve cuántas cargaron.

        Una integración inválida se registra y se saltea: el runtime tiene
        que arrancar aunque un manifest esté roto. Mismo criterio que el
        loader de tools del YAML de agentes.
        """
        root = Path(root) if root is not None else _CATALOG_ROOT
        self._manifests = {}
        if not root.is_dir():
            logger.warning("catálogo de integraciones ausente en %s", root)
            return 0
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            path = directory / "integration.yaml"
            if not path.is_file():
                continue
            try:
                manifest = load_manifest(path)
            except ManifestError as exc:
                logger.error("integración %r inválida, se saltea: %s", directory.name, exc)
                continue
            if manifest.slug != directory.name:
                logger.error(
                    "integración en %s declara metadata.name %r — debe coincidir con "
                    "el nombre del directorio; se saltea.",
                    directory,
                    manifest.slug,
                )
                continue
            try:
                for action in manifest.actions:
                    if action.handler:
                        load_handler(action.handler)
            except HandlerError as exc:
                logger.error(
                    "integración %r tiene un handler irresoluble, se saltea: %s",
                    manifest.slug,
                    exc,
                )
                continue
            self._manifests[manifest.slug] = manifest
        return len(self._manifests)

    def get(self, slug: str) -> IntegrationManifest | None:
        return self._manifests.get(slug)

    def all(self) -> list[IntegrationManifest]:
        return list(self._manifests.values())


_default: IntegrationCatalog | None = None


def default_catalog() -> IntegrationCatalog:
    """Catálogo compartido del proceso, descubierto la primera vez que se pide."""
    global _default
    if _default is None:
        _default = IntegrationCatalog()
        _default.discover()
    return _default


__all__ = ["IntegrationCatalog", "default_catalog"]
