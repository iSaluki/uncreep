#!/usr/bin/env python3
"""Combine identity, manifest audit, tracker scan and pattern scan into analysis/SUMMARY.md, the
agent's starting point for Phase 3 (finding the creepy features).

    scripts/summarise.py <package>
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def main(pkg):
    ws = REPO / "workspace" / pkg
    a = ws / "analysis"
    ident = load(ws / "input" / "IDENTITY.json", {}).get("base.apk", {})
    man = load(a / "manifest.json", {})
    trk = load(a / "trackers.json", None)
    scan = load(a / "scan.json", {})
    exported = [c for c in man.get("components", []) if c["effectively_exported"] and c["tag"] != "activity"]
    md = [f"# Analysis summary: {ident.get('label')} ({pkg} {ident.get('version_name')})", "",
          f"- base.apk SHA-256: `{ident.get('sha256')}`",
          f"- signer(s): " + "; ".join(f"{s['dn']} (`{s['sha256']}`)" for s in ident.get("signers", [])),
          f"- minSdk {ident.get('min_sdk')}, targetSdk {ident.get('target_sdk')}, native code: {ident.get('native_code')}",
          f"- DEX files: {len(list((ws / 'dex').glob('classes*.dex')))}", "",
          "## Capabilities (manifest)", "",
          f"- dangerous permissions ({len(man.get('dangerous_permissions', []))}): "
          + ", ".join(f"`{p.split('.')[-1]}`" for p in man.get("dangerous_permissions", [])),
          f"- notable permissions: " + ", ".join(f"`{p.split('.')[-1]}` ({d})" for p, d in man.get("notable_permissions", {}).items()),
          f"- `<queries>`: {len(man.get('queries', {}).get('packages', []))} packages, "
          f"{len(man.get('queries', {}).get('intents', []))} intents",
          f"- exported services/receivers/providers: {len(exported)}",
          "", "Details: `manifest.md`.", "", "## Third-party SDKs (Exodus signatures)", ""]
    if trk is None:
        md.append("(tracker scan not run)")
    else:
        md += [f"- **{n}** ({', '.join(v['signatures'][:3])})" for n, v in sorted(trk.items())] or ["- none detected"]
    md += ["", "## Pattern-scan leads (hits; read before believing)", "", "| Category | Hits | Top files |", "|---|---|---|"]
    for k, v in sorted(scan.items(), key=lambda kv: -kv[1]["hits"]):
        if v["hits"]:
            md.append(f"| {k} | {v['hits']} | {', '.join('`' + f + '`' for f in v.get('top_files', [])[:3])} |")
    md += ["", "Details: `scan.md`. Next: follow AGENTS.md Phase 3 and write `FINDINGS.md`."]
    (a / "SUMMARY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main(sys.argv[1])
