"""El gate de confirmación: quién dijo que sí, y a qué exactamente.

Este módulo es PURO respecto del modelo: no importa nada del engine, no recibe
mensajes del LLM y no ve su salida. Esa es la propiedad que hace duro al gate —
la decisión de si hubo consentimiento la toma el texto que escribió la persona,
y nunca una interpretación del modelo.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata

# Generoso a propósito. Un gate que sólo acepta un token exacto —que el modelo
# tal vez no le comunicó a la persona— la deja trabada sin forma de avanzar.
# Lo que NO se acepta es una frase: "bueno dale pero cambiame la cantidad" es un
# mensaje nuevo, e interpretarlo sería justo lo que este gate existe para evitar.
CONFIRMACIONES = frozenset({"si", "confirmo", "dale", "ok", "listo"})


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin espacios de los bordes.

    Así `SI`, `Sí` y ` sí ` son el mismo caso y la lista de arriba se escribe
    una sola vez, en su forma normalizada.
    """
    plano = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def es_confirmacion(texto: str | None) -> bool:
    """Si este texto —escrito por una persona— cuenta como un sí."""
    if not texto:
        return False
    return _normalizar(texto) in CONFIRMACIONES


def huella(tool_name: str, args: dict) -> str:
    """Identifica una llamada concreta: la tool Y sus argumentos.

    Que los argumentos entren en la huella es lo que cierra el bypass obvio:
    confirmar un pedido de dos unidades y ejecutar uno de doscientas. Si los
    argumentos cambian es una propuesta nueva, y necesita su propia
    confirmación.

    `sort_keys` para que el mismo pedido con las claves en otro orden dé la
    misma huella; `default=str` para que un argumento no serializable no
    levante en el camino del gate.
    """
    crudo = json.dumps(args or {}, sort_keys=True, default=str)
    return hashlib.sha256(f"{tool_name}\x00{crudo}".encode()).hexdigest()


class Pendientes:
    """Qué propuso el agente en cada sesión, y si la persona ya dijo que sí.

    ponytail: vive en memoria del proceso. El pool del runtime corre con
    `replicas: 1` (astromesh-nexus/deploy/components/runtime-pool/
    deployment.yaml:9), así que hoy alcanza. Si algún día escala, una sesión que
    caiga en otro pod pierde su pendiente y el agente vuelve a preguntar:
    molesto, nunca peligroso, porque `permitido` falla cerrado. La salida es un
    store en Postgres, que es donde ya vive la memoria conversacional.
    """

    def __init__(self) -> None:
        # session_id -> {"fp": huella, "tool": nombre, "ok": bool, "argumentos": dict}
        self._por_sesion: dict[str, dict] = {}

    def registrar(
        self, session_id: str, tool_name: str, fp: str, argumentos: dict | None = None
    ) -> None:
        """El agente propuso esta llamada. Proponer no es autorizar.

        `argumentos` se guarda TAL COMO se propuso — es lo que el runtime usa
        después para redactar, con sus propias palabras, tanto el aviso que le
        cuenta a la persona qué va a pasar (`Agent.run`) como el rechazo que le
        dice al modelo qué está esperando exactamente cuando sus argumentos
        cambian de una llamada a la siguiente.

        Si YA hay algo en el slot de esta sesión, esta llamada NO lo pisa: gana
        la primera propuesta sin usar. El slot es uno solo por sesión — sin
        este guard, una segunda propuesta en la MISMA corrida (un sub-agente,
        un paso de chain, o el mismo agente insistiendo) reemplaza en silencio
        a la primera, y el "sí" que la persona escribe mirando esa primera
        propuesta termina autorizando la segunda, que nunca vio. Se ignora
        tanto si lo que hay está confirmado como si no: un pendiente confirmado
        y sin usar es transitorio (`tool_fn` lo consume antes de ejecutar, o
        `cerrar_si_confirmado` lo barre al final de la corrida) — si sigue ahí
        es porque todavía está en juego, y perder ESE de pisada sería peor.
        """
        if session_id in self._por_sesion:
            return
        self._por_sesion[session_id] = {
            "fp": fp,
            "tool": tool_name,
            "ok": False,
            "argumentos": argumentos or {},
        }

    def habilitar(self, session_id: str, texto: str | None) -> bool:
        """Lee el mensaje de la persona y decide si habilita lo pendiente.

        Un mensaje que NO confirma descarta el pendiente: vence en un turno, así
        no queda un permiso flotando tres mensajes después, cuando la
        conversación ya habla de otra cosa.
        """
        pendiente = self._por_sesion.get(session_id)
        if pendiente is None:
            return False
        if not es_confirmacion(texto):
            del self._por_sesion[session_id]
            return False
        pendiente["ok"] = True
        return True

    def pendiente(self, session_id: str) -> dict | None:
        """Copia de sólo lectura de lo que hay pendiente en esta sesión, si hay algo.

        No consume ni modifica nada — a diferencia de `permitido`/`habilitar`,
        que son parte del gate. Esto lo usa el runtime para redactar texto
        (el aviso de confirmación, el rechazo con el pendiente real cuando los
        argumentos derivan de una llamada a otra), nunca para decidir si algo
        se ejecuta.
        """
        pendiente = self._por_sesion.get(session_id)
        return dict(pendiente) if pendiente is not None else None

    def permitido(self, session_id: str, tool_name: str, fp: str) -> bool:
        """Si esta llamada exacta está autorizada ahora mismo."""
        pendiente = self._por_sesion.get(session_id)
        return bool(
            pendiente
            and pendiente["ok"]
            and pendiente["tool"] == tool_name
            and pendiente["fp"] == fp
        )

    def cerrar(self, session_id: str) -> None:
        """Termina la corrida: una confirmación vale para UNA."""
        self._por_sesion.pop(session_id, None)

    def cerrar_si_confirmado(self, session_id: str) -> None:
        """Como `cerrar`, pero sólo si lo que hay ahora mismo ya fue confirmado.

        Distinto de `cerrar` a secas: si esta corrida consumió una
        confirmación y DESPUÉS propuso algo nuevo, esa propuesta nueva tiene
        que sobrevivir hasta el próximo mensaje. El slot queda libre para
        ella no porque `registrar` pise nada —no pisa, ver su docstring—
        sino porque `tool_fn` ya lo vació con `cerrar()` al consumir la
        confirmación anterior antes de ejecutar. Cerrar acá de nuevo, sin
        mirar `ok`, se comería esa propuesta nueva antes de que la persona
        la vea.
        """
        pendiente = self._por_sesion.get(session_id)
        if pendiente is not None and pendiente["ok"]:
            self._por_sesion.pop(session_id, None)
