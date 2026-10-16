"""`spec.permissions`: qué tools registradas puede ofrecer y ejecutar un agente."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from fnmatch import fnmatchcase

from astromesh.errors import AgentConfigError

logger = logging.getLogger(__name__)

CLAVES_PERMISSIONS = frozenset({"allowed_actions", "denied_actions"})


def _lista(agente, permissions, clave):
    valor = permissions.get(clave)
    if valor is None:
        return None
    if not isinstance(valor, list) or not all(isinstance(p, str) for p in valor):
        raise AgentConfigError(
            f"agent {agente!r}: permissions.{clave} tiene que ser una lista de nombres de "
            "tool (comodines fnmatch)"
        )
    return valor


def resolver_permisos(agent_name, registradas: Iterable[str], permissions) -> frozenset[str] | None:
    """Nombres de tool permitidos, o `None` si el agente no declara restricción."""
    if permissions is None:
        return None
    if not isinstance(permissions, dict):
        raise AgentConfigError(
            f"agent {agent_name!r}: permissions tiene que ser un objeto con "
            "permissions.allowed_actions / permissions.denied_actions: una lista de "
            "nombres de tool (comodines fnmatch)"
        )
    if sobrantes := sorted(set(permissions) - CLAVES_PERMISSIONS):
        logger.warning(
            "agent %r declara permissions con %s que este runtime no lee: %s. Se ignoran. "
            "Si esperabas que hicieran algo, el runtime es viejo para ese manifiesto.",
            agent_name,
            "una clave" if len(sobrantes) == 1 else "claves",
            ", ".join(sobrantes),
        )
    allowed = _lista(agent_name, permissions, "allowed_actions")
    denied = _lista(agent_name, permissions, "denied_actions")
    if allowed is None and denied is None:
        return None

    registradas = sorted(registradas)
    for patron in [*(allowed or []), *(denied or [])]:
        if not any(fnmatchcase(n, patron) for n in registradas):
            logger.warning(
                "agent %r: el patrón %r de permissions no matchea ninguna tool registrada "
                "(registradas: %s)",
                agent_name,
                patron,
                ", ".join(registradas) or "(ninguna)",
            )
    resultado = frozenset(
        n
        for n in registradas
        if (allowed is None or any(fnmatchcase(n, p) for p in allowed))
        and not any(fnmatchcase(n, p) for p in denied or [])
    )
    if registradas and not resultado:
        logger.error("agent %r: permissions deja al agente sin tools", agent_name)
    return resultado
