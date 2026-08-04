"""Escenarios del benchmark, calcados de agentes reales del repo.

Las tools son mockeadas y deterministas a propósito: el benchmark mide el patrón,
y una tool que sale a la red mete variabilidad que ahoga la señal. Cada una duerme
un tiempo fijo para que la ganancia de concurrencia de Glyph sea medible.

Cada schema declara `returns`: la primera corrida contra kimi-k2.5 mostró que sin
eso el modelo inventa los nombres de campo (`is_oem`, `relevance`, `brand`) y el
pipe filtra a vacío en silencio.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from astromesh.rag.agent_rag import format_knowledge

TOOL_LATENCY_S = 0.15


def _schema(
    name: str, description: str, properties: dict, required: list[str], returns: str
) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
            "returns": returns,
        },
    }


@dataclass
class Scenario:
    name: str
    query: str
    tools: list[dict]
    tool_impl: dict[str, Callable]
    expected: Callable[[str], bool]
    reference_program: str
    # Lo que AgentRAG.build_context() inyectaría en el prompt. Vacío en los
    # escenarios que no simulan RAG, para que sigan comparables con las corridas
    # ya versionadas en results-*.md.
    knowledge: str = ""


# ---- autolink-parts ----------------------------------------------------------

_PARTS = [
    {"sku": "OEM-1", "kind": "oem", "price": 90, "rating": 5, "stock": 3},
    {"sku": "AFT-1", "kind": "aftermarket", "price": 40, "rating": 4, "stock": 0},
    {"sku": "AFT-2", "kind": "aftermarket", "price": 55, "rating": 4, "stock": 6},
]


async def _search_parts(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return _PARTS


async def _check_stock(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"sku": args.get("sku"), "eta_days": 5}


async def _quote(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"sku": args.get("sku"), "total": 120}


AUTOLINK = Scenario(
    name="autolink-parts/cotizar-pastillas",
    query="Necesito pastillas de freno para un Corolla 2019. Quiero opción original y alternativa.",
    tools=[
        _schema(
            "search_parts",
            "Busca repuestos por vehículo y tipo de parte",
            {"make": {"type": "string"}, "part": {"type": "string"}},
            ["make", "part"],
            'lista de {sku, kind, price, rating, stock}; kind es "oem" o "aftermarket"',
        ),
        _schema(
            "check_stock",
            "Consulta reposición de un SKU",
            {"sku": {"type": "string"}},
            ["sku"],
            "{sku, eta_days}",
        ),
        _schema(
            "quote",
            "Cotiza un SKU",
            {"sku": {"type": "string"}},
            ["sku"],
            "{sku, total}",
        ),
    ],
    tool_impl={"search_parts": _search_parts, "check_stock": _check_stock, "quote": _quote},
    expected=lambda answer: "OEM-1" in answer or "AFT-2" in answer,
    reference_program=(
        'v = search_parts(make="Toyota", part="pastillas")\n'
        'oem = v | where(kind == "oem") | top(1, by=rating)\n'
        'alt = v | where(kind == "aftermarket", stock > 0) | top(1, by=price)\n'
        "return {oem, alt}"
    ),
)


# ---- support-agent -----------------------------------------------------------


async def _find_order(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"id": args.get("order_id"), "status": "delivered", "days_since": 12}


async def _refund_policy(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"window_days": 30, "requires_receipt": True}


async def _open_ticket(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"ticket": "T-100"}


SUPPORT = Scenario(
    name="support-agent/devolucion",
    query="Compré hace 12 días con la orden A-77 y quiero devolverlo. ¿Puedo?",
    tools=[
        _schema(
            "find_order",
            "Busca una orden",
            {"order_id": {"type": "string"}},
            ["order_id"],
            "{id, status, days_since}",
        ),
        _schema(
            "refund_policy",
            "Consulta la política de devoluciones",
            {},
            [],
            "{window_days, requires_receipt}",
        ),
        _schema(
            "open_ticket",
            "Abre un ticket",
            {"order_id": {"type": "string"}},
            ["order_id"],
            "{ticket}",
        ),
    ],
    tool_impl={
        "find_order": _find_order,
        "refund_policy": _refund_policy,
        "open_ticket": _open_ticket,
    },
    expected=lambda answer: "T-100" in answer or "30" in answer,
    reference_program=(
        'orden = find_order(order_id="A-77")\n'
        "politica = refund_policy()\n"
        "if orden.days_since < politica.window_days:\n"
        '    ticket = open_ticket(order_id="A-77")\n'
        "return {orden, politica, ticket}"
    ),
)


# ---- cadena larga ------------------------------------------------------------
#
# Los dos escenarios de arriba los resolvió ReAct con 2 llamadas al modelo, así
# que no había round-trips que eliminar y Glyph sólo podía perder. Este obliga a
# encadenar: cada dato sale del anterior, y la respuesta necesita los cuatro
# ramales. Es el caso que la hipótesis del diseño ataca.


async def _find_customer(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"customer_id": "C-9", "zip": "1425", "tier": "gold"}


async def _list_devices(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return [
        {"device_id": "D-1", "sku": "LAV-200", "bought_days_ago": 400, "active": True},
        {"device_id": "D-2", "sku": "HEL-050", "bought_days_ago": 120, "active": True},
        {"device_id": "D-3", "sku": "TOS-010", "bought_days_ago": 90, "active": False},
    ]


async def _warranty(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    covered = {"LAV-200": False, "HEL-050": True, "TOS-010": True}
    return {"sku": args.get("sku"), "covered": covered.get(args.get("sku"), False), "months": 12}


async def _service_centers(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return [
        {"center_id": "SC-A", "name": "Centro Palermo", "distance_km": 3, "slots": 2},
        {"center_id": "SC-B", "name": "Centro Caballito", "distance_km": 8, "slots": 5},
    ]


async def _book(args: dict[str, Any]) -> Any:
    await asyncio.sleep(TOOL_LATENCY_S)
    return {"booking_id": "B-777", "center_id": args.get("center_id")}


LONG_CHAIN = Scenario(
    name="service-agent/agendar-reparacion",
    query=(
        "Soy ana@mail.com. Uno de mis electrodomésticos activos anda mal. "
        "Decime cuáles siguen en garantía y agendame en el centro de servicio "
        "más cercano que tenga turnos."
    ),
    tools=[
        _schema(
            "find_customer",
            "Busca un cliente por email",
            {"email": {"type": "string"}},
            ["email"],
            "{customer_id, zip, tier}",
        ),
        _schema(
            "list_devices",
            "Lista los electrodomésticos de un cliente",
            {"customer_id": {"type": "string"}},
            ["customer_id"],
            "lista de {device_id, sku, bought_days_ago, active}",
        ),
        _schema(
            "warranty",
            "Consulta la garantía de un SKU",
            {"sku": {"type": "string"}},
            ["sku"],
            "{sku, covered, months}",
        ),
        _schema(
            "service_centers",
            "Lista centros de servicio cerca de un código postal",
            {"zip": {"type": "string"}},
            ["zip"],
            "lista de {center_id, name, distance_km, slots}",
        ),
        _schema(
            "book",
            "Agenda un turno en un centro",
            {"center_id": {"type": "string"}, "device_id": {"type": "string"}},
            ["center_id", "device_id"],
            "{booking_id, center_id}",
        ),
    ],
    tool_impl={
        "find_customer": _find_customer,
        "list_devices": _list_devices,
        "warranty": _warranty,
        "service_centers": _service_centers,
        "book": _book,
    },
    expected=lambda answer: "B-777" in answer and "SC-A" in answer,
    reference_program=(
        'cliente = find_customer(email="ana@mail.com")\n'
        "equipos = list_devices(customer_id=cliente.customer_id)\n"
        "activos = equipos | where(active == true)\n"
        "garantia = warranty(sku=activos.first.sku)\n"
        "centros = service_centers(zip=cliente.zip)\n"
        "cercano = centros | where(slots > 0) | top(1, by=distance_km, asc=true)\n"
        "turno = book(center_id=cercano.first.center_id, device_id=activos.first.device_id)\n"
        "return {garantia, cercano, turno}"
    ),
)

# ---- el mismo escenario, con knowledge ---------------------------------------
#
# `rendered_prompt` lleva los chunks y se antepone como system en CADA llamada al
# modelo (astromesh/runtime/engine.py:906). Un agente RAG con ReAct y seis vueltas
# paga sus chunks seis veces. Este escenario mide cuánto pesa eso.
#
# Clona a SUPPORT a propósito: es donde Glyph pierde peor (+382% en tokens con
# kimi-k2.7-code-highspeed), porque con dos tools el costo fijo de la gramática
# domina. Si el knowledge da vuelta ESE caso, el multiplicador es fuerte de verdad.

POLITICAS_CHUNKS = [
    {
        "content": (
            "Política de devoluciones — plazo general. El cliente dispone de 30 días "
            "corridos desde la fecha de entrega para solicitar la devolución de un "
            "producto. El plazo se cuenta desde que la orden figura como entregada en "
            "el sistema, no desde la fecha de compra, porque es el dato que el cliente "
            "puede verificar sin ambigüedad y el que registra el courier al confirmar "
            "la recepción. Pasados los 30 días la solicitud se rechaza automáticamente "
            "salvo que aplique alguna de las excepciones detalladas más abajo. El "
            "plazo es el mismo para compras en tienda física y en el canal online, y "
            "no se extiende por feriados ni por fines de semana: si el día 30 cae en "
            "un día no hábil, la solicitud igual debe quedar iniciada antes de la "
            "medianoche de ese día. El sistema envía un recordatorio automático al "
            "cliente cinco días antes de que venza el plazo si la orden no tiene "
            "todavía una solicitud de devolución asociada, para reducir los reclamos "
            "por vencimiento sorpresivo. Las devoluciones parciales, cuando la orden "
            "tiene varios ítems, siguen la misma regla de 30 días por ítem individual, "
            "contados desde la entrega de ese ítem puntual y no desde la entrega del "
            "pedido completo si se despachó en más de un envío."
        )
    },
    {
        "content": (
            "Política de devoluciones — requisitos. Toda devolución exige el "
            "comprobante de compra, que puede ser el ticket físico o el número de "
            "orden asociado a la cuenta del cliente; no se acepta como comprobante "
            "válido una captura de pantalla del carrito ni un correo de confirmación "
            "sin número de orden legible. El producto debe estar en su empaque "
            "original, con todos sus accesorios, manuales y regalos promocionales que "
            "hayan venido incluidos, y sin señales de uso más allá de lo necesario "
            "para probarlo o evaluarlo, tal como se permite en una tienda física. Los "
            "productos de higiene personal y la ropa interior no se aceptan una vez "
            "abiertos, por normativa sanitaria vigente, y esta restricción no admite "
            "excepciones aunque el producto esté con falla. Los electrodomésticos "
            "grandes deben devolverse con el precinto de seguridad intacto cuando "
            "aplique, y el cliente es responsable de retirar sus datos personales de "
            "cualquier dispositivo con memoria antes de iniciar el trámite. Si falta "
            "algún accesorio, el equipo de control de calidad puede aprobar la "
            "devolución con un descuento proporcional en el reembolso en lugar de "
            "rechazarla directamente."
        )
    },
    {
        "content": (
            "Política de devoluciones — excepciones al plazo. Un producto con falla de "
            "fábrica se puede devolver durante todo el período de garantía, que es de "
            "12 meses desde la fecha de entrega, y en ese caso no aplican los "
            "requisitos de empaque original ni de accesorios completos, porque la "
            "devolución se tramita como reclamo de garantía y no como arrepentimiento "
            "de compra. Los productos comprados durante las liquidaciones de fin de "
            "temporada tienen un plazo reducido de 15 días, informado explícitamente "
            "en la ficha del producto al momento de la compra, y este plazo corto no "
            "se extiende aunque el cliente alegue no haber visto el aviso. Las compras "
            "hechas como regalo pueden extender el plazo hasta 60 días si se declara "
            "al momento de la compra marcando la opción correspondiente en el "
            "checkout; si no se declaró como regalo, rige el plazo general de 30 días "
            "aunque el destinatario final no sea quien pagó. Las compras corporativas "
            "con factura A siguen un circuito distinto, gestionado por el equipo de "
            "cuentas empresariales, y no pasan por este flujo de autoservicio."
        )
    },
    {
        "content": (
            "Reembolsos — plazos y medios. El reembolso se acredita en el mismo medio "
            "de pago usado en la compra, sin excepciones, incluso si el cliente pide "
            "explícitamente que se le acredite en otro medio o en saldo a favor. En "
            "tarjeta de crédito puede demorar hasta dos ciclos de facturación, según "
            "el emisor, por lo que el resumen del cliente puede no reflejar el "
            "reembolso inmediatamente después de que el sistema lo procese. En "
            "transferencia y débito el plazo es de 5 a 10 días hábiles desde que se "
            "aprueba la devolución, contados desde la aprobación de control de "
            "calidad y no desde el momento en que el cliente despachó el paquete. No "
            "se emiten reembolsos en efectivo por compras online bajo ninguna "
            "circunstancia, ni siquiera en sucursales físicas, porque el medio de "
            "pago original queda registrado en el sistema de facturación. Si la "
            "compra se hizo combinando saldo a favor y tarjeta, el reembolso "
            "prioriza devolver primero el saldo a favor y luego, si corresponde, el "
            "remanente a la tarjeta."
        )
    },
    {
        "content": (
            "Proceso de devolución — pasos. El agente verifica la orden y la fecha de "
            "entrega, confirma que se cumplan los requisitos de plazo y de estado del "
            "producto, y abre un ticket de devolución que queda asociado a la orden "
            "original para que cualquier agente pueda dar seguimiento sin pedirle al "
            "cliente que repita la explicación. El ticket genera una etiqueta de "
            "envío prepaga que se manda al correo del cliente, junto con instrucciones "
            "de embalaje para minimizar el riesgo de daño en el transporte. El "
            "cliente tiene 10 días corridos desde que recibe la etiqueta para "
            "despachar el paquete; si no lo hace en ese plazo, el ticket se cierra "
            "automáticamente y debe iniciarse uno nuevo. Una vez recibido el producto "
            "en depósito, control de calidad tiene 3 días hábiles para aprobarlo y "
            "disparar el reembolso, o para rechazarlo si no cumple los requisitos, en "
            "cuyo caso el producto se reenvía al cliente sin reembolso y con una "
            "notificación explicando el motivo del rechazo."
        )
    },
]

KNOWLEDGE_POLITICAS = format_knowledge(POLITICAS_CHUNKS)

SUPPORT_RAG = replace(
    SUPPORT,
    name="support-agent-rag/devolucion",
    knowledge=KNOWLEDGE_POLITICAS,
)

SCENARIOS = [AUTOLINK, SUPPORT, SUPPORT_RAG, LONG_CHAIN]
