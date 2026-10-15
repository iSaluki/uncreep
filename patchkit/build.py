#!/usr/bin/env python3
"""Apply an uncreep recipe to an app and produce signed, installable APKs.

    python3 -m patchkit.build --recipe recipes/<package> --input workspace/<package>/input \\
        --out workspace/<package>/out

Steps
  1. check the input is exactly the APK the recipe was written for (SHA-256 and, if the recipe
     pins it, the original signing certificate), unless --force;
  2. disassemble the DEX files with apktool, without decoding resources (many apps' resources
     cannot be rebuilt, so resources.arsc, res/, assets and native libraries are carried over
     byte-for-byte);
  3. run the recipe: patch_manifest() edits the binary manifest, patch_code() edits smali;
     helper classes in the recipe's smali/ folder are added as a new DEX file;
  4. reassemble only the DEX files that were changed, and check each with D8;
  5. rebuild the APK from the original entries, swapping in the patched manifest and DEX files
     and dropping the original signatures; zipalign; sign base and splits with your key;
  6. merge base + splits into one installable APK (APKEditor), unless --no-merge.
"""

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from . import smali
from .manifest import Manifest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"


def log(msg):
    print(msg, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(*cmd, capture=False, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], check=True, text=True,
                       stdout=subprocess.PIPE if capture else None, **kw)
    return r.stdout


def tool(name: str) -> Path:
    env, default = {"apktool": ("APKTOOL_JAR", "apktool.jar"),
                    "build-tools": ("ANDROID_BUILD_TOOLS", "build-tools"),
                    "apkeditor": ("APKEDITOR_JAR", "APKEditor.jar")}[name]
    p = Path(os.environ[env]) if env in os.environ else TOOLS / default
    if not p.exists():
        sys.exit(f"missing {p}: run tools/setup.sh or set ${env}")
    return p


def signer_sha256(apk: Path) -> list[str]:
    out = run(tool("build-tools") / "apksigner", "verify", "--print-certs", apk, capture=True)
    return re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", out)


def min_sdk(apk: Path) -> int:
    out = run(tool("build-tools") / "aapt2", "dump", "badging", apk, capture=True)
    m = re.search(r"^(?:min)?[sS]dkVersion:'(\d+)'", out, re.M)
    return int(m.group(1)) if m else 21


def load_recipe(path: Path):
    f = path / "recipe.py" if path.is_dir() else path
    spec = importlib.util.spec_from_file_location("uncreep_recipe", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in ("PACKAGE", "VERSION", "BASE_SHA256", "patch_manifest", "patch_code"):
        if not hasattr(mod, attr):
            sys.exit(f"recipe {f} is missing {attr}")
    mod.DIR = f.parent
    return mod


def is_signature_entry(name: str) -> bool:
    if name == "stamp-cert-sha256":  # Play source stamp, part of the original signature
        return True
    if not name.startswith("META-INF/"):
        return False
    base = name[len("META-INF/"):]
    return "/" not in base and (base == "MANIFEST.MF" or base.upper().endswith((".SF", ".RSA", ".DSA", ".EC")))


def rebuild_zip(src: Path, dst: Path, replace: dict[str, bytes], add: dict[str, bytes] = None):
    """Copy src to dst entry by entry (same order and compression), replacing some entries,
    dropping the old signature and appending new entries."""
    seen = set()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if is_signature_entry(info.filename):
                continue
            data = replace.get(info.filename)
            if data is None:
                data = zin.read(info.filename)
            else:
                seen.add(info.filename)
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            out.create_system = info.create_system
            zout.writestr(out, data, compress_type=info.compress_type, compresslevel=9)
        for name, data in (add or {}).items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    missing = set(replace) - seen
    if missing:
        raise RuntimeError(f"entries not present in {src.name}: {missing}")


def ensure_keystore(path: Path, alias: str, password: str):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    run("keytool", "-genkeypair", "-keystore", path, "-storepass", password, "-keypass", password,
        "-alias", alias, "-keyalg", "RSA", "-keysize", "4096", "-validity", "10000",
        "-dname", "CN=uncreep local build")


def align_and_sign(unsigned: Path, out: Path, ks: Path, alias: str, password: str):
    bt = tool("build-tools")
    aligned = unsigned.with_suffix(".aligned.apk")
    run(bt / "zipalign", "-f", "-P", "16", "4", unsigned, aligned)
    run(bt / "apksigner", "sign", "--ks", ks, "--ks-key-alias", alias, "--ks-pass", f"pass:{password}",
        "--key-pass", f"pass:{password}", "--out", out, aligned)
    run(bt / "apksigner", "verify", out)
    aligned.unlink()
    Path(str(out) + ".idsig").unlink(missing_ok=True)


def dex_name(smali_dir: str) -> str:
    return "classes.dex" if smali_dir == "smali" else smali_dir.replace("smali_", "") + ".dex"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipe", required=True, type=Path, help="recipes/<package> (folder with recipe.py)")
    ap.add_argument("--input", required=True, type=Path, help="folder with base.apk and any split_*.apk")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, help="scratch folder (default: <out>/../build)")
    ap.add_argument("--keystore", type=Path, default=Path(os.environ.get("UNCREEP_KEYSTORE", REPO / "keystore/uncreep.jks")))
    ap.add_argument("--alias", default="uncreep")
    ap.add_argument("--password", default=os.environ.get("UNCREEP_KEYSTORE_PASSWORD", "uncreep"))
    ap.add_argument("--no-merge", action="store_true", help="only write the signed base + split APKs")
    ap.add_argument("--no-d8-check", action="store_true", help="skip validating patched DEX files with D8")
    ap.add_argument("--force", action="store_true", help="patch even if the input doesn't match the recipe's pins")
    args = ap.parse_args()

    recipe = load_recipe(args.recipe)
    name = getattr(recipe, "OUTPUT_NAME", f"{recipe.PACKAGE}-uncreeped")
    base = args.input / "base.apk"
    splits = sorted(args.input.glob("split_*.apk"))
    if not base.exists():
        sys.exit(f"{base} not found (run: ./uncreep acquire {recipe.PACKAGE})")

    # -- 1. pins ------------------------------------------------------------------------------
    problems = []
    digest = sha256(base)
    if digest != recipe.BASE_SHA256:
        problems.append(f"base APK sha256 {digest} != recipe's {recipe.BASE_SHA256} ({recipe.PACKAGE} {recipe.VERSION})")
    want_signer = getattr(recipe, "SIGNER_SHA256", None)
    if want_signer:
        got = signer_sha256(base)
        if want_signer not in got:
            problems.append(f"base APK signer {got} != recipe's {want_signer}: not the publisher's APK?")
    for p in problems:
        if not args.force:
            sys.exit(p + "\nRecipes target the exact build they were written for. Use --force to try anyway.")
        log("WARNING: " + p)

    work = (args.work or args.out.parent / "build").resolve()
    decoded = work / "decoded"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.apk"):
        old.unlink()

    java = ["java", os.environ.get("UNCREEP_JAVA_HEAP", "-Xmx6g"), "-jar", tool("apktool")]
    run(*java, "d", "--no-res", "--force", "-o", decoded, base)

    # -- 2/3. patch ---------------------------------------------------------------------------
    m = Manifest(zipfile.ZipFile(base).read("AndroidManifest.xml"), log)
    recipe.patch_manifest(m)
    manifest = m.to_bytes()

    existing = sorted((d.name for d in decoded.glob("smali*")), key=lambda n: int(n[13:] or 1) if n != "smali" else 1)
    helpers = recipe.DIR / "smali"
    new_dex = None
    if helpers.is_dir() and any(helpers.rglob("*.smali")):
        n = 1 + max(1 if d == "smali" else int(d.replace("smali_classes", "")) for d in existing)
        new_dir = decoded / f"smali_classes{n}"
        shutil.copytree(helpers, new_dir)
        smali.TOUCHED.update(new_dir.rglob("*.smali"))
        new_dex = dex_name(new_dir.name)
        log(f"helpers: {len(list(helpers.rglob('*.smali')))} class(es) from {helpers} -> {new_dex}")

    recipe.patch_code(decoded, log)

    dex_dirs = sorted({p.relative_to(decoded).parts[0] for p in smali.TOUCHED})
    log(f"modified DEX files: {', '.join(dex_name(d) for d in dex_dirs) or 'none'}")

    # -- 4. reassemble only the touched DEX files (park the rest so apktool skips them) --------
    replace, add = {"AndroidManifest.xml": manifest}, {}
    if dex_dirs:
        parked = work / "parked"
        parked.mkdir()
        for d in decoded.glob("smali*"):
            if d.name not in dex_dirs:
                d.rename(parked / d.name)
        run(*java, "b", "-o", work / "apktool-out.apk", decoded)
        min_api = min_sdk(base)
        for d in dex_dirs:
            dex = dex_name(d)
            data = (decoded / "build" / "apk" / dex).read_bytes()
            if not args.no_d8_check:
                check = work / "d8-check"
                shutil.rmtree(check, ignore_errors=True)
                (check / "out").mkdir(parents=True)
                (check / dex).write_bytes(data)
                # D8 rejects structurally invalid bytecode (bad registers, broken branches, ...)
                run(tool("build-tools") / "d8", "--release", "--min-api", min_api, "--output", check / "out",
                    check / dex)
            (add if dex == new_dex else replace)[dex] = data

    # -- 5. package, align, sign --------------------------------------------------------------
    ensure_keystore(args.keystore, args.alias, args.password)
    unsigned = work / "base.unsigned.apk"
    rebuild_zip(base, unsigned, replace, add)
    outputs = [args.out / f"{name}-base.apk" if splits else args.out / f"{name}.apk"]
    align_and_sign(unsigned, outputs[0], args.keystore, args.alias, args.password)
    for split in splits:
        unsigned = work / f"{split.stem}.unsigned.apk"
        rebuild_zip(split, unsigned, {})
        outputs.append(args.out / f"{name}-{split.stem.removeprefix('split_')}.apk")
        align_and_sign(unsigned, outputs[-1], args.keystore, args.alias, args.password)

    # -- 6. merge -----------------------------------------------------------------------------
    if splits and not args.no_merge:
        merge_in = work / "merge-in"
        merge_in.mkdir()
        for p in outputs:
            shutil.copy(p, merge_in / p.name)
        merged = work / "merged.unsigned.apk"
        run("java", os.environ.get("UNCREEP_JAVA_HEAP", "-Xmx6g"), "-jar", tool("apkeditor"), "m", "-i", merge_in, "-o", merged)
        check = Manifest(zipfile.ZipFile(merged).read("AndroidManifest.xml"), log)
        if check.root.get("requiredSplitTypes") is not None:
            sys.exit("merged APK still requires splits")
        # Re-pack with Python's zipfile: APKEditor's local headers make zipalign print thousands
        # of (harmless) "header mismatch" warnings.
        repacked = work / "merged.repacked.apk"
        rebuild_zip(merged, repacked, {})
        align_and_sign(repacked, args.out / f"{name}.apk", args.keystore, args.alias, args.password)
        log(f"\nDone. Single APK: {args.out / (name + '.apk')}")
        log(f"Split set:        adb install-multiple {' '.join(str(p) for p in outputs)}")
    else:
        log(f"\nDone: {' '.join(str(p) for p in outputs)}")


if __name__ == "__main__":
    main()
