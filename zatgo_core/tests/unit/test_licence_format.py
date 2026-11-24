"""Licence file format and Ed25519 signatures (no database; throwaway keys)."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
import uuid
from datetime import date

from zatgo_core.licensing import crypto, edition_config, licence_format
from zatgo_core.licensing.licence_format import LicenceError


def payload(**kw):
    base = {
        "schema_version": 1, "licence_id": str(uuid.uuid4()), "licence_number": "ZGL-2026-00001",
        "licence_version": 1, "product_id": "zatgo_erp", "customer_id": "C-1", "customer_name": "Acme",
        "site_ids": ["11111111-1111-4111-8111-111111111111"], "site_names": [], "edition_id": "sales",
        "edition_name": "ZatGo Sales", "edition_version": 1,
        "features": edition_config.get_preset("sales")["features"], "modules": ["sales"],
        "licence_type": "Yearly", "issue_date": "2026-01-01", "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "grace_days": 0, "platforms": {"desk": 1, "desktop": 0, "mobile": 0},
        "limits": {"max_users": 5, "max_companies": 1, "max_sites": 1}, "device_policy": "none",
        "issued_at": "2026-01-01T00:00:00", "key_id": "x",
    }
    base.update(kw)
    return base


class _Keys(unittest.TestCase):
    def setUp(self) -> None:
        self.key = crypto.generate_private_key()
        self.kid = crypto.key_id(self.key.public_key())
        crypto.trust_for_tests({self.kid: crypto.b64e(crypto.raw_public(self.key.public_key()))})

    def tearDown(self) -> None:
        crypto.trust_for_tests(None)


class TestEnvelope(_Keys):
    def test_round_trip(self) -> None:
        text = licence_format.seal(payload(), self.key)
        body, raw, env = licence_format.open_envelope(text)
        self.assertEqual(body["customer_name"], "Acme")
        self.assertEqual(body["key_id"], self.kid)
        self.assertEqual(env["key_id"], self.kid)
        self.assertEqual(raw, licence_format.canonical(body))
        licence_format.validate_payload(body)

    def _tamper(self, text: str, mutate) -> str:
        env = json.loads(text)
        body = json.loads(base64.b64decode(env["payload"]))
        mutate(body)
        env["payload"] = crypto.b64e(licence_format.canonical(body))
        return json.dumps(env)

    def test_any_change_breaks_the_signature(self) -> None:
        text = licence_format.seal(payload(), self.key)
        for mutate in (lambda b: b.update(customer_name="Evil"),
                       lambda b: b["features"].update({"inventory.stock_transfer": []}),
                       lambda b: b.update(expiry_date="2099-12-31"),
                       lambda b: b["limits"].update(max_users=0)):
            with self.subTest(mutate=mutate), self.assertRaises(LicenceError) as ctx:
                licence_format.open_envelope(self._tamper(text, mutate))
            self.assertEqual(ctx.exception.code, "bad_signature")

    def test_signature_swap_and_garbage(self) -> None:
        a = json.loads(licence_format.seal(payload(customer_name="A"), self.key))
        b = json.loads(licence_format.seal(payload(customer_name="B"), self.key))
        a["signature"] = b["signature"]
        with self.assertRaises(LicenceError) as ctx:
            licence_format.open_envelope(json.dumps(a))
        self.assertEqual(ctx.exception.code, "bad_signature")
        for junk in ("not json", "[]", json.dumps({"type": "zatgo.licence", "format": 1, "key_id": self.kid,
                                                    "payload": "%%%", "signature": "%%%"})):
            with self.assertRaises(LicenceError):
                licence_format.open_envelope(junk)

    def test_untrusted_key_is_refused(self) -> None:
        other = crypto.generate_private_key()
        with self.assertRaises(LicenceError) as ctx:
            licence_format.open_envelope(licence_format.seal(payload(), other))
        self.assertEqual(ctx.exception.code, "unknown_key")

    def test_non_canonical_payload_is_refused_even_when_signed(self) -> None:
        body = payload(key_id=self.kid)
        raw = json.dumps(body, indent=2).encode()  # valid JSON, valid signature, not canonical
        env = {"type": "zatgo.licence", "format": 1, "key_id": self.kid, "payload": crypto.b64e(raw),
               "signature": crypto.b64e(crypto.sign(self.key, raw))}
        with self.assertRaises(LicenceError) as ctx:
            licence_format.open_envelope(json.dumps(env))
        self.assertEqual(ctx.exception.code, "not_canonical")

    def test_wrong_file_types(self) -> None:
        with self.assertRaises(LicenceError) as ctx:
            licence_format.open_envelope(json.dumps(edition_config.get_preset("sales")))
        self.assertEqual(ctx.exception.code, "wrong_type")
        revocation = licence_format.seal({"product_id": "zatgo_erp", "revoked": [], "issued_at": "x"}, self.key,
                                         kind=licence_format.REVOCATION_TYPE)
        with self.assertRaises(LicenceError):
            licence_format.open_envelope(revocation)
        body, _raw, _env = licence_format.open_envelope(revocation, kind=licence_format.REVOCATION_TYPE)
        self.assertEqual(licence_format.validate_revocation(body), [])

    def test_floats_are_not_allowed(self) -> None:
        with self.assertRaises(LicenceError):
            licence_format.canonical({"a": 1.5})


class TestPayload(unittest.TestCase):
    def test_a_good_payload(self) -> None:
        licence_format.validate_payload(payload())

    def test_each_rule(self) -> None:
        cases = {
            "unsupported_schema": payload(schema_version=2),
            "wrong_product": payload(product_id="other"),
            "invalid_dates": payload(expiry_date="2025-01-01"),
            "unknown_features": payload(features={"sales.future_thing": []}),
            "invalid_features": payload(features={"sales.invoice": ["import"]}),
        }
        for code, body in cases.items():
            with self.subTest(code=code), self.assertRaises(LicenceError) as ctx:
                licence_format.validate_payload(body)
            self.assertEqual(ctx.exception.code, code)
        for body in (payload(site_ids=[]), payload(licence_id="nope"), payload(licence_version=0),
                     payload(licence_type="Forever"), payload(limits={"max_users": -1}),
                     payload(site_ids=["a", "b"], limits={"max_sites": 1})):
            with self.assertRaises(LicenceError):
                licence_format.validate_payload(body)
        with self.assertRaises(LicenceError):
            licence_format.validate_payload(payload(licence_type="Perpetual"))  # has an expiry
        licence_format.validate_payload(payload(licence_type="Perpetual", expiry_date=None))

    def test_status_and_days(self) -> None:
        p = payload()
        self.assertEqual(licence_format.status(p, date(2025, 12, 31)), "Scheduled")
        self.assertEqual(licence_format.status(p, date(2026, 6, 1)), "Active")
        self.assertEqual(licence_format.status(p, date(2026, 12, 15)), "Expiring")
        self.assertEqual(licence_format.status(p, date(2027, 1, 1)), "Expired")
        self.assertEqual(licence_format.status(payload(licence_type="Trial"), date(2026, 6, 1)), "Trial")
        self.assertEqual(licence_format.days_remaining(p, date(2026, 12, 21)), 10)
        self.assertIsNone(licence_format.days_remaining(payload(licence_type="Lifetime", expiry_date=None),
                                                       date(2026, 6, 1)))


class TestPrivateKeyRules(unittest.TestCase):
    def test_key_file_location_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sites = os.path.join(tmp, "sites")
            os.makedirs(sites)
            inside = os.path.join(sites, "key.pem")
            outside = os.path.join(tmp, "key.pem")
            key = crypto.generate_private_key()
            crypto.write_private_key(key, inside)
            crypto.write_private_key(key, outside)
            with self.assertRaises(crypto.KeyError_):
                crypto.load_private_key(inside, sites_dir=sites)
            loaded = crypto.load_private_key(outside, sites_dir=sites)
            self.assertEqual(crypto.key_id(loaded.public_key()), crypto.key_id(key.public_key()))
            os.chmod(outside, 0o644)
            with self.assertRaises(crypto.KeyError_):
                crypto.load_private_key(outside, sites_dir=sites)
            with self.assertRaises(FileExistsError):
                crypto.write_private_key(key, outside)

    def test_shipped_keys_file_is_valid(self) -> None:
        for kid, raw in crypto.shipped_keys().items():
            self.assertEqual(crypto.key_id(base64.b64decode(raw)), kid)


if __name__ == "__main__":
    unittest.main()
