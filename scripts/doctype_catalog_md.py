"""Render the catalog JSON as docs/DOCTYPE_CATALOG.md."""
import json
import sys

rows = json.load(open(sys.argv[1]))
out = [
    "# DocType catalog",
    "",
    "*Phase 4, generated 2026-11-28 from the DocType JSON on `main` (after the `v0_6_0` rename). Regenerate with "
    "`scripts/doctype_catalog.py` rather than editing by hand.*",
    "",
    "Column keys:",
    "- **Kind**: regular, single (settings), child (table rows), submittable.",
    "- **Naming**: the `autoname` rule.",
    "- **Req**: mandatory fields.",
    "- **Unique / Index**: database-level unique keys and search indexes.",
    "- **Links**: Link targets.",
    "- **Children**: child tables.",
    "- **Roles**: roles in its DocPerms.",
    "- **History**: `track_changes` (version history).",
    "- **Hooks**: controller methods.",
    "- **Refs**: files that name it outside its own folder (code / tests).",
    "",
]
for module in sorted({r["module"] for r in rows}):
    out += [f"## {module}", "", "| DocType | Kind | Naming | Fields | Req | Unique | Index | Links | Children | Roles | History | Hooks | Refs |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in rows if r["module"] == module), key=lambda r: (r["kind"] == "child", r["name"])):
        def j(items, n=4):
            items = list(items)
            return ", ".join(items[:n]) + (f" +{len(items) - n}" if len(items) > n else "") if items else "—"
        out.append(
            f"| {r['name']} | {r['kind']} | `{r['naming']}` | {r['fields']} | {j(r['reqd'])} | {j(r['unique'])} | {j(r['index'])} | "
            f"{j(r['links'])} | {j(r['tables'])} | {j(r['roles'], 3)} | {'yes' if r['track_changes'] else 'no'} | {j(r['hooks'])} | "
            f"{r['code_refs']} / {r['test_refs']} |"
        )
    out.append("")
open(sys.argv[2], "w").write("\n".join(out))
print(len(rows), "rows written")
