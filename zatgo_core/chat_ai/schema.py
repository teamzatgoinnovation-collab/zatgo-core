"""Schema bits Frappe's DocType JSON cannot express. Idempotent; called from
install.bootstrap() on every migrate, so a patch that was only *recorded* as
run can never leave the index missing (see .claude/rules/accounting.md)."""

from __future__ import annotations

import frappe

FULLTEXT_INDEXES = (
	# (table, index name, column) -- conversation search over message text
	("tabAI Chat Message", "ft_chat_ai_message_content", "content"),
	("tabAI Chat Session", "ft_chat_ai_session_title", "title"),
)


def _has_index(table: str, name: str) -> bool:
	return bool(
		frappe.db.sql(
			"""select 1 from information_schema.STATISTICS
			where TABLE_SCHEMA = database() and TABLE_NAME = %s and INDEX_NAME = %s limit 1""",
			(table, name),
		)
	)


def ensure_fulltext_indexes() -> list[str]:
	"""Create missing FULLTEXT indexes; returns the ones created."""
	if frappe.db.db_type != "mariadb":
		return []
	created = []
	for table, name, column in FULLTEXT_INDEXES:
		if not frappe.db.table_exists(table.removeprefix("tab")) or _has_index(table, name):
			continue
		try:
			frappe.db.commit()  # DDL commits implicitly in MariaDB
			frappe.db.sql_ddl(f"alter table `{table}` add fulltext index `{name}` (`{column}`)")
			created.append(name)
		except Exception:
			frappe.log_error(title=f"chat_ai fulltext index {name}")
	return created


def ensure_schema() -> None:
	ensure_fulltext_indexes()
