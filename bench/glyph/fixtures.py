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
from dataclasses import dataclass
from typing import Any

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

SCENARIOS = [AUTOLINK, SUPPORT, LONG_CHAIN]
