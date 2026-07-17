"""Desk module definition for ZatGo Core."""

from frappe import _


def get_data():
    return [
        {
            "module_name": "ZatGo Core",
            "type": "module",
            "label": _("ZatGo Core"),
            "color": "blue",
            "icon": "octicon octicon-gear",
            "description": _("Foundation settings for the ZatGo ERP ecosystem"),
        }
    ]
