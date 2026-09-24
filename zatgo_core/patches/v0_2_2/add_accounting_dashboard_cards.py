"""Today's Sales / Today's Purchases Number Cards + Register report links
on the standard "Invoicing" workspace (ERPNext's day-to-day accounting hub
-- Payment Entry, Sales/Purchase Invoice, Taxes all live there already).

Uses the same building blocks ERPNext's own shipped cards on this exact
workspace already use (Number Card with a Timespan filter + a dynamic
company filter -- see erpnext/selling/number_card/annual_sales) and the
same Card+Link grouping ERPNext/zatca_erpgulf already use for report
links on this bench -- not the newer "Workspace Shortcut" block type,
which has zero working examples anywhere on this install and isn't worth
gambling on for a two-link addition.

Purely additive: existing content blocks, links and number cards on the
workspace are left untouched; this only appends.
"""

from __future__ import annotations

import json

import frappe

NUMBER_CARDS = [
    {
        "name": "Today's Sales",
        "label": "Today's Sales",
        "document_type": "Sales Invoice",
        "aggregate_function_based_on": "base_grand_total",
        "filters_json": json.dumps(
            [
                ["Sales Invoice", "posting_date", "Timespan", "today"],
                ["Sales Invoice", "docstatus", "=", "1"],
            ]
        ),
    },
    {
        "name": "Today's Purchases",
        "label": "Today's Purchases",
        "document_type": "Purchase Invoice",
        "aggregate_function_based_on": "base_grand_total",
        "filters_json": json.dumps(
            [
                ["Purchase Invoice", "posting_date", "Timespan", "today"],
                ["Purchase Invoice", "docstatus", "=", "1"],
            ]
        ),
    },
]

REGISTER_LINKS = [
    {"label": "Sales Register", "report": "Sales Register"},
    {"label": "Purchase Register", "report": "Purchase Register"},
]


def execute() -> None:
    if not frappe.db.exists("DocType", "Workspace"):
        return
    _ensure_number_cards()
    _ensure_workspace_additions()
    frappe.db.commit()


def _ensure_number_cards() -> None:
    for card in NUMBER_CARDS:
        if frappe.db.exists("Number Card", card["name"]):
            continue
        frappe.get_doc(
            {
                "doctype": "Number Card",
                "name": card["name"],
                "label": card["label"],
                "document_type": card["document_type"],
                "type": "Document Type",
                "function": "Sum",
                "aggregate_function_based_on": card["aggregate_function_based_on"],
                "filters_json": card["filters_json"],
                "dynamic_filters_json": json.dumps(
                    [[card["document_type"], "company", "=", 'frappe.defaults.get_user_default("Company")']]
                ),
                "is_public": 1,
                "is_standard": 0,
                "module": "Accounts",
                "show_percentage_stats": 1,
                "stats_time_interval": "Daily",
            }
        ).insert(ignore_permissions=True)


def _ensure_workspace_additions() -> None:
    if not frappe.db.exists("Workspace", "Invoicing"):
        return
    doc = frappe.get_doc("Workspace", "Invoicing")
    content = json.loads(doc.content)

    existing_number_cards = {b["data"].get("number_card_name") for b in content if b.get("type") == "number_card"}
    existing_cards = {b["data"].get("card_name") for b in content if b.get("type") == "card"}

    # Splice the two new number_card blocks right after the existing four
    # (same col:3 sizing), before the "Reports & Masters" header -- keeps
    # the untouched blocks' relative order identical either way.
    header_idx = next((i for i, b in enumerate(content) if b.get("type") == "header"), len(content))
    inserted_number_cards = False
    for card in reversed(NUMBER_CARDS):
        if card["label"] in existing_number_cards:
            continue
        content.insert(
            header_idx,
            {"id": frappe.generate_hash(length=10), "type": "number_card", "data": {"number_card_name": card["label"], "col": 3}},
        )
        inserted_number_cards = True

    inserted_reports_card = False
    if "Reports" not in existing_cards:
        content.append({"id": frappe.generate_hash(length=10), "type": "card", "data": {"card_name": "Reports", "col": 4}})
        inserted_reports_card = True

    if not inserted_number_cards and not inserted_reports_card:
        return  # already applied, nothing new to add

    doc.content = json.dumps(content)

    if inserted_reports_card:
        max_idx = max((row.idx for row in doc.links), default=0)
        max_idx += 1
        doc.append(
            "links",
            {
                "type": "Card Break",
                "label": "Reports",
                "idx": max_idx,
            },
        )
        for link in REGISTER_LINKS:
            max_idx += 1
            doc.append(
                "links",
                {
                    "type": "Link",
                    "label": link["label"],
                    "link_type": "Report",
                    "link_to": link["report"],
                    "is_query_report": 1,
                    "idx": max_idx,
                },
            )

    doc.save(ignore_permissions=True)
