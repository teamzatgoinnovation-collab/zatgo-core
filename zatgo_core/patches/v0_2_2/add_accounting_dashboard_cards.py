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

# NOTE: Number Card has a `filters_config` field, but the workspace widget
# (frappe/public/js/frappe/widgets/number_card_widget.js) never reads it --
# the rendered tile only ever offers "Refresh"/"Edit" actions, no live
# filter UI. Don't set it here expecting an adjustable date picker on the
# tile; that isn't a capability this widget has.

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
            # show_full_number wasn't set by an earlier run of this patch --
            # without it, a card whose value is exactly 0 renders "NaN"
            # (Frappe's shorten_number() returns "" for a falsy 0, which
            # cascades into NaN in the widget's downstream number-format
            # conversion). Re-sync it onto already-created cards too.
            frappe.db.set_value("Number Card", card["name"], "show_full_number", 1)
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
                "show_full_number": 1,
                "stats_time_interval": "Daily",
            }
        ).insert(ignore_permissions=True)


def _ensure_workspace_additions() -> None:
    if not frappe.db.exists("Workspace", "Invoicing"):
        return
    doc = frappe.get_doc("Workspace", "Invoicing")
    content = json.loads(doc.content)

    # The "content" JSON only controls layout (block order/col span) -- the
    # workspace renderer resolves each number_card block by matching its
    # data.number_card_name against a *label* in the separate `number_cards`
    # child table, then reads that row's own number_card_name to know which
    # real Number Card doc to render. A content block with no matching
    # `number_cards` row silently renders nothing -- both must be kept in
    # sync, which is why this checks each one independently below.
    existing_content_refs = {b["data"].get("number_card_name") for b in content if b.get("type") == "number_card"}
    existing_child_labels = {row.label for row in doc.number_cards}
    existing_cards = {b["data"].get("card_name") for b in content if b.get("type") == "card"}

    changed = False

    # Splice new number_card blocks right after the existing four (same
    # col:3 sizing), before the "Reports & Masters" header -- keeps the
    # untouched blocks' relative order identical either way.
    header_idx = next((i for i, b in enumerate(content) if b.get("type") == "header"), len(content))
    for card in reversed(NUMBER_CARDS):
        if card["label"] not in existing_content_refs:
            content.insert(
                header_idx,
                {"id": frappe.generate_hash(length=10), "type": "number_card", "data": {"number_card_name": card["label"], "col": 3}},
            )
            changed = True
        if card["label"] not in existing_child_labels:
            doc.append("number_cards", {"number_card_name": card["name"], "label": card["label"]})
            changed = True

    inserted_reports_card = "Reports" not in existing_cards
    if inserted_reports_card:
        content.append({"id": frappe.generate_hash(length=10), "type": "card", "data": {"card_name": "Reports", "col": 4}})
        changed = True

    if not changed:
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
