"""Regenerate workspace/zatgo_erp/zatgo_erp.json from SECTIONS in services/erp_workspace.py.

Run after editing SECTIONS (no bench needed):  python3 scripts/build_zatgo_erp_workspace.py
"""

import importlib.util
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("erp_workspace", root / "zatgo_core" / "services" / "erp_workspace.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

out = root / "zatgo_core" / "zatgo_core" / "workspace" / "zatgo_erp" / "zatgo_erp.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(mod.workspace_json(), indent=1, sort_keys=True) + "\n")
print("wrote", out)
