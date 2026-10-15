#!/usr/bin/env python3
"""Print and record what an input folder contains: package, version, SDK levels, SHA-256 and
signing certificates of every APK. Writes <input>/IDENTITY.json.

    scripts/identity.py workspace/<package>/input

Check the base APK's certificate against the real publisher before trusting a mirror download
(compare with a copy from the Play Store, the publisher's website, or a previous version).
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BT = Path(__file__).resolve().parent.parent / "tools" / "build-tools"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(inp: Path):
    out = {}
    for apk in sorted(inp.glob("*.apk"), key=lambda p: p.name != "base.apk"):
        certs = subprocess.run([BT / "apksigner", "verify", "--print-certs", apk], text=True,
                               capture_output=True)
        info = {"sha256": sha256(apk),
                "signature_valid": certs.returncode == 0,
                "signers": [{"dn": dn, "sha256": h} for dn, h in zip(
                    re.findall(r"certificate DN: (.+)", certs.stdout),
                    re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", certs.stdout))]}
        if apk.name == "base.apk":
            badge = subprocess.run([BT / "aapt2", "dump", "badging", apk], text=True, capture_output=True).stdout
            g = lambda rx: (re.search(rx, badge) or [None, None])[1]
            info |= {"package": g(r"package: name='([^']+)'"), "version_name": g(r"versionName='([^']*)'"),
                     "version_code": g(r"versionCode='(\d+)'"), "min_sdk": g(r"minSdkVersion:'(\d+)'"),
                     "target_sdk": g(r"targetSdkVersion:'(\d+)'"), "label": g(r"application-label:'([^']*)'"),
                     "native_code": re.findall(r"native-code: (.*)", badge)}
        out[apk.name] = info
    (inp / "IDENTITY.json").write_text(json.dumps(out, indent=1))
    b = out.get("base.apk", {})
    print(f"{b.get('label')}  {b.get('package')} {b.get('version_name')} ({b.get('version_code')})  "
          f"minSdk {b.get('min_sdk')} targetSdk {b.get('target_sdk')}")
    print(f"  base.apk sha256 {b.get('sha256')}")
    for s in b.get("signers", []):
        print(f"  signer   {s['dn']}\n           cert sha256 {s['sha256']}")
    if not b.get("signature_valid"):
        print("  WARNING: base.apk signature does not verify")
    splits = [n for n in out if n != "base.apk"]
    if splits:
        print(f"  {len(splits)} split(s): {', '.join(n[6:-4] for n in splits)}")
        bad = [n for n in splits if {x['sha256'] for x in out[n]['signers']} != {x['sha256'] for x in b.get('signers', [])}]
        if bad:
            print(f"  WARNING: splits signed differently from base: {bad}")
    print(f"written {inp / 'IDENTITY.json'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
