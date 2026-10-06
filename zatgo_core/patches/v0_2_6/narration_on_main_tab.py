"""Move the Narration (+ new Attachment field) to the main tab.

Same code as patches/v0_2_5/add_narration_fields.py, which now produces the
main-tab layout and also undoes its first version (narration on the More
Info tab). Listed separately so existing sites re-run it on migrate.
"""

from __future__ import annotations


def execute() -> None:
    from zatgo_core.patches.v0_2_5.add_narration_fields import execute as apply_narration_layout

    apply_narration_layout()
