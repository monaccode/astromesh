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


#: Lo que el modelo lee cuando una tool con confirmación no se ejecutó.
_MENSAJE_PENDIENTE = (
    "Ya hay una propuesta esperando confirmación. "
    "Contale a la persona exactamente qué vas a hacer "
    "con estos argumentos y pedile que responda SI. Si "
    "ya te habían dicho que sí, repetí EXACTAMENTE "
    "estos argumentos — no los vuelvas a redactar de "
    "memoria."
)


def gate(pendientes: Pendientes, session_id: str, tool_name: str, args: dict) -> dict | None:
    """La compuerta de una tool con confirmación, antes de ejecutarla.

    `None` = puede ejecutarse, y la licencia YA se consumió. Si no, devuelve la
    observación de rechazo para el modelo.

    Rechazo: se registra la propuesta (si el slot está libre — si no,
    `registrar` no pisa lo que ya había, ver su docstring) y se devuelve el
    pendiente REAL: `tool` + `argumentos` tal como quedaron guardados, no los
    que esta llamada acaba de intentar. Sin esto, un modelo que re-deriva los
    argumentos de memoria en vez de repetirlos (p.ej. "pedido de 2 cajas" →
    "pedido de dos cajas") ve un rechazo genérico, no sabe qué cambió, y puede
    quemar un "sí" ya dicho sin ejecutar nada — el `mensaje` le dice
    explícitamente que repita ESTO, no que proponga de nuevo a ciegas.

    Paso: se consume ACÁ, antes de ejecutar — no al final de la corrida. Un
    "sí" autoriza esta llamada UNA vez: sin este `cerrar`, `permitido` seguía
    devolviendo True el resto de la corrida y un patrón que reintenta (o un
    modelo que alucina el mismo llamado dos veces) volvía a escribir con la
    misma confirmación. Incondicional a `desde_humano`: la licencia ya fue
    otorgada por una corrida humana anterior de esta sesión (`habilitar` es lo
    único que gatea eso), así que usarla una vez la agota sea quien sea quien
    la usó.
    """
    fp = huella(tool_name, args)
    if not pendientes.permitido(session_id, tool_name, fp):
        pendientes.registrar(session_id, tool_name, fp, args)
        pendiente = pendientes.pendiente(session_id)
        return {
            "error": "confirmacion_requerida",
            "pendiente": {"tool": pendiente["tool"], "argumentos": pendiente["argumentos"]},
            "mensaje": _MENSAJE_PENDIENTE,
        }
    pendientes.cerrar(session_id)
    return None


def _truncar(texto: str, limite: int) -> str:
    """Misma salida que `engine._truncate` (sin importar el engine)."""
    if not texto:
        return ""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + f"\n... [truncated at {len(texto)} chars]"


def aviso_confirmacion(tool_name: str, argumentos: dict) -> str:
    """La frase que le dice a la persona qué va a pasar si confirma.

    La escribe el runtime, nunca el modelo — es la pieza que cierra el bypass
    de "el modelo le pregunta una cosa a la persona y usa el sí para otra":
    lo que la persona lee acá es, por construcción, lo mismo que `gate` va
    a dejar ejecutar si responde que sí.

    Los argumentos se listan `clave: valor` en vez de volcar el dict crudo:
    un `{'monto': 999999}` con comillas y llaves es ruido en un chat de
    WhatsApp.

    El orden de inserción del dict lo controla el MODELO — es él quien arma
    `arguments` para la tool call. Truncar el string ya renderizado (como
    hacía la versión anterior) dejaba que un argumento de texto libre puesto
    primero se comiera el resto: `aviso_confirmacion('praxis_crear_record',
    {'nota': 'x'*480, 'monto': 999999})` cortaba antes de llegar a `monto`.
    Eso convierte el aviso en algo que el modelo puede curar en vez de un
    disclosure real. Por eso se ordenan las claves (alfabético, no depende
    del modelo) y se trunca CADA VALOR por separado con un tope chico: así
    toda clave aparece siempre, con una porción acotada de su valor. 80 chars
    alcanza para leer un monto, un ID o el arranque de un texto libre sin que
    un solo argumento gigante tape a los demás; el corte de 500 en el total
    ya no hace falta con el tope por valor.

    Dos límites que este aviso NO cierra, a propósito:
    - Si la corrida lanza DESPUÉS de que `gate` registró el pendiente, el
      bloque que arma este aviso nunca se ejecuta (vive después del loop del
      agente) y el `finally` que envuelve la corrida no toca pendientes en
      `ok=False`. El pendiente sobrevive sin que nadie lo haya mostrado, y un
      "si" en el próximo turno lo ejecutaría. Acotado en la práctica — ese
      turno fallido no se persiste, así que el modelo tendría que rearmar los
      mismos argumentos de memoria — pero real.
    - La garantía de esta función es "se redactó", no "le llegó a la
      persona": si el envío por el canal (WhatsApp, etc.) falla después de
      que `result["answer"]` ya lleva el aviso, quien recibe el error no vio
      el detalle, y el pendiente sigue vivo para el próximo turno.
    """
    claves = sorted((argumentos or {}).keys())
    partes = ", ".join(f"{k}: {_truncar(str(argumentos[k]), 80)}" for k in claves)
    detalle = f"{tool_name} con {partes}" if partes else tool_name
    return f"Para confirmar respondé SI. Voy a ejecutar: {detalle}"


def con_aviso(pendientes: Pendientes, session_id: str, answer: object) -> str:
    """`answer` con el aviso de confirmación pegado, si esta sesión tiene un
    pendiente sin confirmar (`ok=False`: lo registró esta corrida); si no,
    `answer` como str.

    Todos los patrones del repo arman "answer" como str — la conversión es
    sólo para no romper si el día de mañana alguno no lo hace.
    """
    respuesta = "" if answer is None else answer if isinstance(answer, str) else str(answer)
    pendiente = pendientes.pendiente(session_id)
    if pendiente is None or pendiente["ok"]:
        return respuesta
    aviso = aviso_confirmacion(pendiente["tool"], pendiente["argumentos"])
    return f"{respuesta}\n\n{aviso}" if respuesta else aviso
