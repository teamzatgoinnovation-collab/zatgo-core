"""String-transform coverage for the Kasib Asia Tax Invoice customer-ids edit
(Arabic name, CR Number, wider invoice-number box). Fixtures are the original
template's relevant fragments, copied from kasibasia before the edit."""

from __future__ import annotations

import unittest

from zatgo_core.setup.ensure_print_formats import _kasib_asia_customer_ids_transform as transform

_HTML = """{% set customer_tax_id = "" %}
{% set customer_cr = "" %}

{% if doc.customer %}
  {% set customer_cr =
    frappe.db.get_value(
      "Customer",
      doc.customer,
      "tax_id"
    ) or ""
  %}
{% endif %}
    <div class="dynamic-field invoice-number center">
      {{ doc.name or "" }}
    </div>
    <div class="dynamic-field customer-name-arabic" dir="rtl">
      {{ doc.customer_name_arabic or doc.customer or "" }}
    </div>
    <div
     <span>س.ت : CR</span>
      class="dynamic-field customer-cr center"
      dir="ltr"
    >
      {{ customer_cr }}
    </div>
        ٠٥٧٩٧٧٦٧٨٠cr
"""

_CSS = """.invoice-number {
    left: 69.51%;
    top: 19.44%;

    width: 16.75%;
    height: 2.81%;
}

.customer-cr {
    right: 3.9%;
    top: 24.93%;

    width: 35.46%;
    height: 3.00%;

    font-size: 10pt;

    line-height: 8.92mm;
}
"""


class TestKasibAsiaCustomerIds(unittest.TestCase):
    def test_original_template_is_fixed(self) -> None:
        html, css, skipped = transform(_HTML, _CSS)
        self.assertEqual(skipped, [])
        # CR comes from the CR field, never the VAT field.
        self.assertIn('"zatgo_cr_number"', html)
        self.assertNotIn('"tax_id"', html)
        # Arabic name comes from the real field, with no English fallback.
        self.assertIn('"zatgo_customer_name_ar"', html)
        self.assertIn("{{ customer_name_ar }}", html)
        self.assertNotIn("customer_name_arabic", html)
        # CR block is well-formed and conditional.
        self.assertIn('class="dynamic-field customer-cr"', html)
        self.assertIn('<span class="cr-en" dir="ltr">CR :</span>', html)
        self.assertNotIn("<div\n     <span>", html)
        # Invoice-number box widened; long numbers shrink.
        self.assertIn("inv_no_len > 20", html)
        self.assertIn("left: 66%;", css)
        self.assertIn("width: 20.5%;", css)
        self.assertNotIn("69.51%", css)
        # Stray "cr" typo gone.
        self.assertNotIn("٠cr", html)

    def test_idempotent(self) -> None:
        once = transform(_HTML, _CSS)
        twice = transform(once[0], once[1])
        self.assertEqual((twice[0], twice[1]), (once[0], once[1]))
        self.assertEqual(twice[2], [])

    def test_unrecognised_format_is_left_alone_and_reported(self) -> None:
        html, css, skipped = transform("<div>custom</div>", "body{}")
        self.assertEqual((html, css), ("<div>custom</div>", "body{}"))
        self.assertEqual(len(skipped), 6)
