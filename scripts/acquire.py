#!/usr/bin/env python3
"""Phase 1: get the app and lay it out as workspace/<package>/input/{base.apk, split_*.apk}.

    scripts/acquire.py <package>[@version] [--source apk-pure] [--arch arm64-v8a]
    scripts/acquire.py <package> --file path/to/app.apk|.xapk|.apks|.apkm

Sources (via EFF's apkeep): apk-pure (default, a third-party mirror), google-play (needs
--email/--token, see apkeep docs), f-droid, huawei-app-gallery. Whatever the source, the
signing certificate is printed so it can be checked against the real publisher.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"


def sh(*cmd, capture=False):
    print("$ " + " ".join(map(str, cmd)), flush=True)
    r = subprocess.run([str(c) for c in cmd], text=True, stdout=subprocess.PIPE if capture else None)
    if r.returncode:
        raise SystemExit(f"command failed ({r.returncode}): {cmd[0]}")
    return r.stdout


def fdroid_direct(pkg: str, version: str | None, dest: Path) -> Path:
    """apkeep's F-Droid index parsing is fragile; fall back to the public F-Droid API."""
    try:
        with urllib.request.urlopen(f"https://f-droid.org/api/v1/packages/{pkg}") as r:
            info = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"F-Droid has no package {pkg} (HTTP {e.code})")
    vc = info["suggestedVersionCode"]
    if version:
        hits = [p["versionCode"] for p in info["packages"] if p["versionName"] == version]
        if not hits:
            raise SystemExit(f"F-Droid has no {pkg} {version}; available: {[p['versionName'] for p in info['packages']]}")
        vc = hits[0]
    out = dest / f"{pkg}_{vc}.apk"
    print(f"downloading https://f-droid.org/repo/{out.name}")
    urllib.request.urlretrieve(f"https://f-droid.org/repo/{out.name}", out)
    return out


def download(pkg, version, source, arch, extra, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    before = set(dest.iterdir())
    app = f"{pkg}@{version}" if version else pkg
    opts = ["acknowledge_dangers=true"] if source == "apk-pure" else []
    if arch and source in ("apk-pure", "google-play"):
        opts.append(f"arch={arch}")
    cmd = [TOOLS / "apkeep", "-a", app, "-d", source] + (["-o", ",".join(opts)] if opts else []) + extra + [dest]
    r = subprocess.run([str(c) for c in cmd], text=True, capture_output=True)
    print(r.stdout + r.stderr)
    new = [p for p in set(dest.iterdir()) - before if p.suffix in (".apk", ".xapk", ".apks", ".apkm")]
    if not new and source == "f-droid":
        return fdroid_direct(pkg, version, dest)
    if not new and source == "google-play":
        # Play downloads land in a folder of base + split APKs
        dirs = [p for p in set(dest.iterdir()) - before if p.is_dir()]
        if dirs:
            return dirs[0]
    if len(new) != 1:
        raise SystemExit(f"download failed (apkeep source {source}); try another --source or supply --file")
    return new[0]


def normalise(src: Path, inp: Path, pkg: str):
    """Write base.apk and split_<name>.apk files into `inp`."""
    shutil.rmtree(inp, ignore_errors=True)
    inp.mkdir(parents=True)
    if src.is_dir():
        apks = {p.name: p.read_bytes() for p in src.glob("*.apk")}
    elif src.suffix == ".apk":
        apks = {"base.apk": src.read_bytes()}
    else:
        with zipfile.ZipFile(src) as z:
            apks = {Path(n).name: z.read(n) for n in z.namelist() if n.endswith(".apk")}
            if any(n.endswith(".obb") for n in z.namelist()):
                print("note: the bundle contains OBB expansion files; they are not modified or delivered")
    base = [n for n in apks if n in ("base.apk", f"{pkg}.apk")] or \
           [n for n in apks if not re.match(r"(split_)?config\.|split_", n)]
    if len(base) != 1:
        raise SystemExit(f"can't tell which APK is the base among {sorted(apks)}")
    (inp / "base.apk").write_bytes(apks.pop(base[0]))
    for n, data in apks.items():
        stem = re.sub(r"^split_", "", n[:-4])
        if stem.startswith(pkg + "."):
            stem = stem[len(pkg) + 1:]
        (inp / f"split_{stem}.apk").write_bytes(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app", help="package name, optionally @version")
    ap.add_argument("--source", default="apk-pure", choices=["apk-pure", "google-play", "f-droid", "huawei-app-gallery"])
    ap.add_argument("--arch", default="arm64-v8a", help="ABI for split bundles (most phones: arm64-v8a)")
    ap.add_argument("--file", type=Path, help="use an APK/XAPK/APKS/APKM you already have")
    ap.add_argument("--email", help="google-play only")
    ap.add_argument("--token", help="google-play only (AAS token)")
    args = ap.parse_args()

    pkg, _, version = args.app.partition("@")
    ws = REPO / "workspace" / pkg
    if args.file:
        src = args.file
    else:
        extra = (["-e", args.email] if args.email else []) + (["-t", args.token] if args.token else [])
        src = download(pkg, version or None, args.source, args.arch, extra, ws / "download")
    normalise(src, ws / "input", pkg)
    print()
    sh(sys.executable, REPO / "scripts" / "identity.py", ws / "input")


if __name__ == "__main__":
    main()
