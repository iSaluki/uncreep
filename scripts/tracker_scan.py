#!/usr/bin/env python3
"""Detect third-party tracker SDKs by matching Exodus Privacy code signatures against the class
descriptors in every DEX file of the given APKs (no decompilation needed).

    scripts/tracker_scan.py workspace/<package>/analysis/trackers.json workspace/<package>/input/*.apk

A hit means the SDK's classes are bundled, not that it is switched on; some apps also only
probe for an SDK by name, which produces false positives. Confirm in the code.
"""

import json
import re
import sys
import zipfile
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "tools" / "exodus-trackers.json"


def main(out, apks):
    if not DB.exists():
        sys.exit(f"{DB} missing: run tools/setup.sh")
    sigs = []
    for t in json.load(open(DB))["trackers"].values():
        for part in (t.get("code_signature") or "").split("|"):
            part = part.strip().rstrip(".")
            if part:
                sigs.append((t["name"], t.get("website", ""), part,
                             ("L" + part.replace("\\.", "/").replace(".", "/")).encode()))
    blob = b""
    for apk in apks:
        with zipfile.ZipFile(apk) as z:
            for n in z.namelist():
                if re.fullmatch(r"classes\d*\.dex", n):
                    blob += z.read(n)
    found = {}
    for name, site, sig, desc in sigs:
        if desc in blob:
            found.setdefault(name, {"website": site, "signatures": []})["signatures"].append(sig)
    Path(out).write_text(json.dumps(found, indent=1))
    print(f"trackers ({len(found)}): {', '.join(sorted(found)) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
