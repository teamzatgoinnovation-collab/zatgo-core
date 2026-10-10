"""Space Order controller."""

import re

import frappe
from frappe.model.document import Document

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED = {
	"www",
	"erp",
	"space",
	"bench",
	"api",
	"mail",
	"ftp",
	"ns1",
	"ns2",
	"cdn",
	"admin",
	"status",
	"docs",
	"app",
	"apps",
	"portal",
}


class SpaceOrder(Document):
	def validate(self):
		slug = (self.slug or "").strip().lower()
		self.slug = slug
		if not SLUG_RE.match(slug):
			frappe.throw("Invalid subdomain slug")
		if slug in RESERVED:
			frappe.throw(f"Subdomain '{slug}' is reserved")
		suffix = frappe.conf.get("space_domain_suffix") or "zatgo.online"
		self.hostname = f"{slug}.{suffix}"
		if not self.desk_url:
			self.desk_url = f"https://{self.hostname}"
