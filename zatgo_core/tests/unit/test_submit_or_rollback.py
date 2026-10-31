"""services/idempotency.submit_or_rollback and the two Payment Entry entry points built on one shared function.

No database: `frappe` is replaced inside the module under test."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from zatgo_core.services import idempotency


class _FakeValidationError(Exception):
    pass


def _fake_frappe():
    fake = MagicMock()
    fake.ValidationError = _FakeValidationError

    def _throw(message, exc=Exception):
        raise exc(message)

    fake.throw.side_effect = _throw
    fake.get_traceback.return_value = "traceback text"
    return fake


class TestSubmitOrRollback(unittest.TestCase):
    def test_success_submits_then_commits_and_does_not_roll_back(self) -> None:
        fake, doc = _fake_frappe(), MagicMock()
        with patch.object(idempotency, "frappe", fake):
            idempotency.submit_or_rollback(doc, log_title="t", failure="nope")
        doc.submit.assert_called_once()
        fake.db.commit.assert_called_once()
        fake.db.rollback.assert_not_called()
        fake.log_error.assert_not_called()

    def test_failure_rolls_back_logs_the_traceback_and_raises_the_message(self) -> None:
        fake, doc = _fake_frappe(), MagicMock()
        doc.submit.side_effect = RuntimeError("stock short")
        with patch.object(idempotency, "frappe", fake):
            with self.assertRaises(_FakeValidationError) as ctx:
                idempotency.submit_or_rollback(doc, log_title="Sale submit failed", failure="Could not post.")
        self.assertEqual(str(ctx.exception), "Could not post.")
        fake.db.rollback.assert_called_once()
        fake.db.commit.assert_not_called()
        fake.log_error.assert_called_once_with(title="Sale submit failed", message="traceback text")

    def test_failure_can_be_built_from_the_exception(self) -> None:
        fake, doc = _fake_frappe(), MagicMock()
        doc.submit.side_effect = RuntimeError("stock short")
        with patch.object(idempotency, "frappe", fake):
            with self.assertRaises(_FakeValidationError) as ctx:
                idempotency.submit_or_rollback(doc, log_title="t", failure=lambda exc: f"Could not post: {exc}.")
        self.assertEqual(str(ctx.exception), "Could not post: stock short.")

    def test_ignore_permissions_is_set_only_when_asked(self) -> None:
        fake = _fake_frappe()
        for asked in (False, True):
            doc = MagicMock()
            doc.flags = MagicMock(ignore_permissions=False)
            with patch.object(idempotency, "frappe", fake):
                idempotency.submit_or_rollback(doc, log_title="t", failure="x", ignore_permissions=asked)
            self.assertEqual(doc.flags.ignore_permissions, asked)


class TestPaymentEntryEntryPoints(unittest.TestCase):
    def test_receive_and_pay_share_one_function_and_keep_their_own_wording(self) -> None:
        from zatgo_core.services import erpnext_writes as w

        with patch.object(w, "_create_invoice_payment", return_value={"ok": True}) as shared:
            w.create_receive_payment("SINV-1", amount=5, client_id="c1")
            w.create_pay_payment("PINV-1", amount=7, client_id="c2")
        (receive, pay) = shared.call_args_list
        self.assertEqual(receive.args[:4], ("Sales Invoice", "sales_invoice", "SINV-1", "Sales Invoice must be submitted before receiving payment"))
        self.assertEqual(pay.args[:4], ("Purchase Invoice", "purchase_invoice", "PINV-1", "Purchase Invoice must be submitted before paying"))
        self.assertEqual((receive.args[4], receive.args[10]), (5, "c1"))
        self.assertEqual((pay.args[4], pay.args[10]), (7, "c2"))


if __name__ == "__main__":
    unittest.main()
