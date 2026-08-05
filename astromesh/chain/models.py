"""Modelos de `spec.chain`: la declaración de encadenamiento en el YAML del agente."""

from __future__ import annotations

from dataclasses import dataclass, field

_MODOS = ("sequential", "parallel")
_INPUT_POR_DEFECTO = "{{ output.answer }}"


@dataclass
class ChainLink:
    """Un eslabón: un agente a disparar, con su condición y su política de fallo."""

    agent: str
    when: str | None = None
    input: str = _INPUT_POR_DEFECTO
    default: bool = False
    retry: dict | None = None
    timeout_seconds: int | None = None
    on_error: str | None = None


@dataclass
class ChainSpec:
    """La cadena completa de un agente."""

    mode: str = "sequential"
    max_depth: int = 5
    links: list[ChainLink] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> ChainSpec:
        mode = raw.get("mode", "sequential")
        if mode not in _MODOS:
            raise ValueError(f"chain.mode inválido: {mode!r} (esperado uno de {_MODOS})")

        max_depth = raw.get("max_depth", 5)
        if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 1:
            raise ValueError(f"chain.max_depth debe ser un entero >= 1, llegó {max_depth!r}")

        crudos = raw.get("on_complete") or []
        if not crudos:
            raise ValueError("chain.on_complete no puede estar vacío")

        links = [cls._parse_link(c, i) for i, c in enumerate(crudos)]

        defaults = [link for link in links if link.default]
        if len(defaults) > 1:
            nombres = ", ".join(link.agent for link in defaults)
            raise ValueError(f"chain.on_complete tiene más de una regla default: {nombres}")

        if mode == "parallel":
            cls._rechazar_referencias_entre_hermanos(links)

        return cls(mode=mode, max_depth=max_depth, links=links)

    @staticmethod
    def _parse_link(raw: dict, idx: int) -> ChainLink:
        agent = raw.get("agent")
        if not agent:
            raise ValueError(f"chain.on_complete[{idx}] no declara `agent`")

        es_default = bool(raw.get("default", False))
        when = raw.get("when")
        if es_default and when is not None:
            raise ValueError(
                f"chain.on_complete[{idx}] ({agent}) declara `default` y `when` a la vez: "
                "un default dispara cuando ningún `when` matcheó, no puede tener el suyo"
            )

        return ChainLink(
            agent=agent,
            when=when,
            input=raw.get("input") or _INPUT_POR_DEFECTO,
            default=es_default,
            retry=raw.get("retry"),
            timeout_seconds=raw.get("timeout_seconds"),
            on_error=raw.get("on_error"),
        )

    @staticmethod
    def _rechazar_referencias_entre_hermanos(links: list[ChainLink]) -> None:
        """En `parallel` las guardas se evalúan todas antes de arrancar cualquier
        rama, así que un `when` que mira a un hermano queda siempre falso. Se
        rechaza en bootstrap en vez de dejarlo fallar callado en producción."""
        hermanos = {link.agent for link in links}
        for link in links:
            if not link.when:
                continue
            for hermano in hermanos:
                if f"steps.{hermano}" in link.when:
                    raise ValueError(
                        f"el `when` del eslabón '{link.agent}' referencia a 'steps.{hermano}', "
                        "un hermano de la misma cadena `parallel`. En paralelo todas las "
                        "guardas se evalúan antes de que corra ninguna rama, así que esa "
                        "condición sería siempre falsa. Usá mode: sequential."
                    )
