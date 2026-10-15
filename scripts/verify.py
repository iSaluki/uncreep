#!/usr/bin/env python3
"""Phase 5 check: compare the patched APK with the original and run the static checks.

    scripts/verify.py <package> [--apk workspace/<package>/out/<name>.apk] [--method 'com/foo/Bar->baz()V' ...]

Checks: signature verifies, 16 KB zip alignment, package name and version unchanged, and a diff
of permissions, <queries>, exported components and meta-data. With --method, decompiles the
patched class with JADX and prints that method so the change can be read back.
Writes workspace/<package>/out/VERIFY.md.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from androguard.core.apk import APK
from androguard.util import set_log

set_log("ERROR")
REPO = Path(__file__).resolve().parent.parent
BT = REPO / "tools" / "build-tools"
NS = "{http://schemas.android.com/apk/res/android}"


def facts(path):
    a = APK(str(path))
    m = a.get_android_manifest_xml()
    app = m.find("application")
    perms = {e.get(NS + "name") for t in ("uses-permission", "uses-permission-sdk-23") for e in m.findall(t)}
    queries = set()
    for q in m.findall("queries"):
        queries |= {"package " + p.get(NS + "name") for p in q.findall("package")}
        for i in q.findall("intent"):
            queries.add("intent " + ",".join(x.get(NS + "name") for x in i.findall("action")) + " " +
                        ",".join(x.get(NS + "scheme") or "" for x in i.findall("data")))
    comps, exported = set(), set()
    for tag in ("activity", "activity-alias", "service", "receiver", "provider"):
        for c in app.findall(tag):
            comps.add(c.get(NS + "name"))
            filt = bool(c.findall("intent-filter"))
            if c.get(NS + "exported") == "true" or (c.get(NS + "exported") is None and filt):
                exported.add(c.get(NS + "name"))
    meta = {f"{x.get(NS + 'name')}={x.get(NS + 'value')}" for x in app.iter("meta-data")}
    dex = sorted(n for n in zipfile.ZipFile(path).namelist() if re.fullmatch(r"classes\d*\.dex", n))
    return {"package": a.get_package(), "version": (a.get_androidversion_name(), a.get_androidversion_code()),
            "permissions": perms, "queries": queries, "components": comps, "exported": exported,
            "meta-data": meta, "dex": dex}


def check(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--apk", type=Path)
    ap.add_argument("--method", action="append", default=[], help="'com/foo/Bar->name' to decompile and show")
    args = ap.parse_args()
    ws = REPO / "workspace" / args.package
    orig = ws / "input" / "base.apk"
    apk = args.apk or next((p for p in sorted((ws / "out").glob("*.apk")) if not re.search(r"-(base|config\.[^-]+)\.apk$", p.name)), None) \
        or next(iter(sorted((ws / "out").glob("*-base.apk"))), None)
    if not apk:
        sys.exit(f"no APK in {ws / 'out'}: run ./uncreep build {args.package}")

    md = [f"# Verification: {apk.name}", ""]
    ok_sig, out = check([BT / "apksigner", "verify", "-v", apk])
    md.append(f"- signature: {'OK' if ok_sig else 'FAILED'} ({', '.join(re.findall(r'Verified using (v\S+ scheme[^:]*): true', out)) or out[-200:]})")
    ok_al, _ = check([BT / "zipalign", "-c", "-P", "16", "4", apk])
    md.append(f"- zipalign (16 KB pages): {'OK' if ok_al else 'FAILED'}")

    a, b = facts(orig), facts(apk)
    same = a["package"] == b["package"] and a["version"] == b["version"]
    md.append(f"- package/version unchanged: {'OK' if same else 'CHANGED'} ({b['package']} {b['version'][0]})")
    md.append(f"- DEX files: {len(a['dex'])} -> {len(b['dex'])}")
    for key in ("permissions", "queries", "exported", "components", "meta-data"):
        removed, added = sorted(a[key] - b[key]), sorted(b[key] - a[key])
        md += ["", f"## {key}: {len(removed)} removed, {len(added)} added", ""]
        merge_note = lambda x: " (expected: split/store metadata dropped by the merge)" \
            if key == "meta-data" and re.match(r"com\.android\.(vending|stamp)\.", x) else ""
        md += [f"- removed `{x}`{merge_note(x)}" for x in removed] + [f"- added `{x}`" for x in added]

    for spec in args.method:
        cls, _, name = spec.partition("->")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([REPO / "tools" / "jadx" / "bin" / "jadx", "--no-res", "--single-class",
                            cls.replace("/", "."), "-d", tmp, apk], capture_output=True)
            src = next(Path(tmp).rglob("*.java"), None)
            text = src.read_text() if src else "(class not found)"
        lines = text.split("\n")
        hits = [i for i, l in enumerate(lines) if re.search(rf"\b{re.escape(name.split('(')[0])}\(", l)
                and re.search(r"(public|private|protected|static|final|void)\s", l)]
        md += ["", f"## `{spec}` (decompiled from the patched APK)", "", "```java"]
        for i in hits[:3]:
            depth, j = 0, i
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                md.append(lines[j])
                j += 1
                if depth <= 0 and "{" in "".join(lines[i:j]):
                    break
        md.append("```")

    (ws / "out" / "VERIFY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if not (ok_sig and ok_al and same):
        sys.exit(1)


if __name__ == "__main__":
    main()
