"""Escenarios del benchmark, calcados de agentes reales del repo.

Las tools son mockeadas y deterministas a propósito: el benchmark mide el patrón,
y una tool que sale a la red mete variabilidad que ahoga la señal. Cada una duerme
un tiempo fijo para que la ganancia de concurrencia de Glyph sea medible.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

TOOL_LATENCY_S = 0.15


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
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
        ),
        _schema(
            "check_stock", "Consulta reposición de un SKU", {"sku": {"type": "string"}}, ["sku"]
        ),
        _schema("quote", "Cotiza un SKU", {"sku": {"type": "string"}}, ["sku"]),
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
        _schema("find_order", "Busca una orden", {"order_id": {"type": "string"}}, ["order_id"]),
        _schema("refund_policy", "Consulta la política de devoluciones", {}, []),
        _schema("open_ticket", "Abre un ticket", {"order_id": {"type": "string"}}, ["order_id"]),
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

SCENARIOS = [AUTOLINK, SUPPORT]
