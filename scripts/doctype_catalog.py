"""Build the DocType catalog of a zatgo_core tree from its DocType JSON and code references (read-only, no Frappe).

    python3 scripts/doctype_catalog.py . catalog.json   # then render docs/DOCTYPE_CATALOG.md from catalog.json
"""
import collections
import glob
import json
import os
import re
import sys

ROOT = sys.argv[1]
PKG = os.path.join(ROOT, "zatgo_core")
LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}

docs = {}
for f in sorted(glob.glob(os.path.join(PKG, "**", "doctype", "*", "*.json"), recursive=True)):
    d = json.load(open(f))
    if d.get("doctype") != "DocType" or os.path.basename(os.path.dirname(f)) + ".json" != os.path.basename(f):
        continue
    d["_dir"] = os.path.dirname(f)
    docs[d["name"]] = d

code = {}
for f in glob.glob(os.path.join(PKG, "**", "*"), recursive=True):
    if not f.endswith((".py", ".js", ".json", ".html")) or "__pycache__" in f or "/node_modules/" in f:
        continue
    try:
        code[f] = open(f, errors="ignore").read()
    except IsADirectoryError:
        pass


def refs(name, own_dir):
    pat = re.compile(r"[\"']" + re.escape(name) + r"[\"']")
    hits = [f for f, t in code.items() if not f.startswith(own_dir) and "/patches/" not in f and pat.search(t)]
    tests = [f for f in hits if "/tests/" in f]
    return len(hits) - len(tests), len(tests)


def kind(d):
    if d.get("istable"):
        return "child"
    if d.get("issingle"):
        return "single"
    if d.get("is_submittable"):
        return "submittable"
    if d.get("is_tree"):
        return "tree"
    return "regular"


rows = []
for name, d in docs.items():
    fields = [x for x in d.get("fields", []) if x.get("fieldtype") not in LAYOUT]
    links = sorted({x["options"] for x in fields if x.get("fieldtype") == "Link" and x.get("options")})
    tables = sorted({x["options"] for x in fields if x.get("fieldtype") in ("Table", "Table MultiSelect") and x.get("options")})
    ctrl = os.path.join(d["_dir"], os.path.basename(d["_dir"]) + ".py")
    methods = []
    if os.path.exists(ctrl):
        methods = re.findall(r"^\s{4}def ([a-z_]+)\(", open(ctrl).read(), re.M)
    hooks = [m for m in methods if m in ("validate", "before_insert", "after_insert", "on_update", "before_save", "on_submit",
                                          "on_cancel", "on_trash", "autoname", "before_validate", "onload", "before_rename")]
    code_refs, test_refs = refs(name, d["_dir"])
    rows.append({
        "module": d.get("module"), "name": name, "kind": kind(d), "naming": d.get("autoname") or "hash/prompt",
        "fields": len(fields), "reqd": [x["fieldname"] for x in fields if x.get("reqd")],
        "unique": [x["fieldname"] for x in fields if x.get("unique")],
        "index": [x["fieldname"] for x in fields if x.get("search_index")],
        "links": links, "tables": tables,
        "roles": sorted({p["role"] for p in d.get("permissions", [])}),
        "track_changes": bool(d.get("track_changes")), "hooks": hooks,
        "code_refs": code_refs, "test_refs": test_refs,
    })

json.dump(rows, open(sys.argv[2], "w"), indent=1)
by = collections.Counter(r["kind"] for r in rows)
print("doctypes", len(rows), dict(by))
print("no code reference outside own folder:", [r["name"] for r in rows if r["code_refs"] == 0 and r["kind"] != "child"])
print("no track_changes (non-child, non-log):", sum(1 for r in rows if not r["track_changes"] and r["kind"] != "child"))
print("no perms:", [r["name"] for r in rows if not r["roles"] and r["kind"] != "child"])
print("All/Guest perms:", [r["name"] for r in rows if set(r["roles"]) & {"All", "Guest"}])
print("links to missing DocTypes (not ours, check ERPNext):", sorted({l for r in rows for l in r["links"] if l not in docs})[:60])
