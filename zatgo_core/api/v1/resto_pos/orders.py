"""Resto POS orders — ZG Order DocType. Thin wrappers over resto_pos_service."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_service as svc


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 50, status: str | None = None) -> dict[str, Any]:
    return svc.list_orders(page=page, page_size=page_size, status=status)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return svc.get_order(name)


@frappe.whitelist()
def create(
    table: str | None = None,
    covers: int | str = 1,
    channel: str = "counter",
    items: Any = None,
    note: str | None = None,
    customer_id: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    delivery: Any = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    return svc.create_order(
        table=table,
        covers=covers,
        channel=channel,
        items=items,
        note=note,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery=delivery,
        company=company,
        client_id=client_id,
    )


@frappe.whitelist()
def add_item(
    order_id: str,
    item_code: str,
    qty: float | str = 1,
    extras: Any = None,
    rate: float | str | None = None,
    station: str | None = None,
) -> dict[str, Any]:
    return svc.add_item(order_id, item_code, qty=qty, extras=extras, rate=rate, station=station)


@frappe.whitelist()
def update_item_qty(order_id: str, item_row: str, qty: float | str) -> dict[str, Any]:
    return svc.update_item_qty(order_id, item_row, qty)


@frappe.whitelist()
def send(order_id: str) -> dict[str, Any]:
    return svc.send_order(order_id)


@frappe.whitelist()
def set_note(order_id: str, note: str) -> dict[str, Any]:
    return svc.set_note(order_id, note)


@frappe.whitelist()
def void(order_id: str) -> dict[str, Any]:
    return svc.void_order(order_id)


@frappe.whitelist()
def give_to_delivery(order_id: str) -> dict[str, Any]:
    return svc.give_to_delivery(order_id)
