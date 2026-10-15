#!/usr/bin/env bash
# Phase 6: hand the patched APK to the user.
#
#   scripts/deliver.sh <package>                     stage workspace/<package>/release/ and print how to install
#   scripts/deliver.sh <package> --github-release    + publish it as a GitHub Release with `gh` (PRIVATE repos only)
#   scripts/deliver.sh <package> --release-branch --confirm-private
#                                                    + commit it to release/ in 45 MB parts; pushing that commit
#                                                      makes .github/workflows/release.yml publish a Release
#                                                      (for agents that can git push but have no `gh`)
#
# Patched APKs contain the original publisher's code. Never publish them from a public
# repository, and never commit them to one: see DISCLAIMER.md and docs/delivery.md.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PKG="${1:?usage: scripts/deliver.sh <package> [--github-release | --release-branch --confirm-private]}"
shift
MODE=local; CONFIRMED=0
for a in "$@"; do
  case "$a" in
    --github-release) MODE=gh ;;
    --release-branch) MODE=branch ;;
    --confirm-private) CONFIRMED=1 ;;
    *) echo "unknown option $a" >&2; exit 1 ;;
  esac
done

WS="$REPO/workspace/$PKG"
OUT="$WS/out"
REL="$WS/release"
ls "$OUT"/*.apk >/dev/null 2>&1 || { echo "nothing in $OUT: run ./uncreep build $PKG" >&2; exit 1; }

VERSION=$(python3 -c "import json;print(json.load(open('$WS/input/IDENTITY.json'))['base.apk']['version_name'])")
TAG="$PKG-$VERSION-uncreeped-$(date -u +%Y%m%d%H%M)"

rm -rf "$REL" && mkdir -p "$REL"
cp "$OUT"/*.apk "$REL"/
( cd "$REL" && sha256sum *.apk > SHA256SUMS )
echo "$TAG" > "$REL/TAG"
{
  echo "Patched build of \`$PKG\` $VERSION made with [uncreep](https://github.com/iSaluki/uncreep)."
  echo
  if [ -f "$REPO/recipes/$PKG/FINDINGS.md" ]; then
    echo "## What was removed"; echo
    python3 - "$REPO/recipes/$PKG/FINDINGS.md" <<'PY'
import re, sys
text = re.sub(r"<!--.*?-->", "", open(sys.argv[1]).read(), flags=re.S)
m = re.search(r"^## Removed\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
print((m.group(1).strip() if m else "") or "(see FINDINGS.md)")
PY
    echo
  fi
  echo "## Install"; echo
  echo "Uninstall the store version first (the signing key differs, so Android refuses to update over it)."
  echo "Then open the single \`.apk\` on the phone, or \`adb install <file>.apk\`."
  echo
  echo "**Not tested on a device unless stated above. Use at your own risk; see DISCLAIMER.md.**"
  echo "Contains the original publisher's code: for your own private use only, do not redistribute."
} > "$REL/NOTES.md"

echo "staged in $REL:"
ls -la "$REL"

case "$MODE" in
  local)
    cat <<MSG

Give the user the APK directly:
  - same machine:   adb install "$(ls "$REL"/*.apk | grep -v -- '-base\|-config\.' | head -1)"
  - agent tool:     send the file with a file-sharing tool if your harness has one
  - cloud session:  ./uncreep deliver $PKG --github-release   (or --release-branch --confirm-private)
MSG
    ;;
  gh)
    command -v gh >/dev/null || { echo "gh not installed: use --release-branch instead" >&2; exit 1; }
    PRIV=$(cd "$REPO" && gh api 'repos/{owner}/{repo}' -q .private) || PRIV=unknown
    if [ "$PRIV" != "true" ]; then
      echo "REFUSING: this repository is not confirmed private (private=$PRIV). Publishing a modified" >&2
      echo "app publicly redistributes someone else's software. Use a private copy (see docs/delivery.md)." >&2
      exit 1
    fi
    cd "$REL"
    gh release create "$TAG" *.apk SHA256SUMS --title "$PKG $VERSION (uncreeped)" --notes-file NOTES.md
    ;;
  branch)
    if [ "$CONFIRMED" != 1 ]; then
      echo "REFUSING: pass --confirm-private after checking that the git remote is a PRIVATE repository." >&2
      echo "Anything pushed to a public repository is published, and stays in its history." >&2
      exit 1
    fi
    DST="$REPO/release"
    rm -rf "$DST" && mkdir -p "$DST"
    for f in "$REL"/*.apk; do
      split -b 45m -d -a 2 "$f" "$DST/$(basename "$f").part"   # GitHub rejects files over 100 MB
    done
    cp "$REL/SHA256SUMS" "$REL/TAG" "$REL/NOTES.md" "$DST"/
    cat > "$DST/join.sh" <<'SH'
#!/bin/sh
# Reassemble the APKs from their parts and check them against SHA256SUMS.
set -e
cd "$(dirname "$0")"
for f in $(sed 's/.*  //' SHA256SUMS); do cat "$f".part* > "$f"; done
sha256sum -c SHA256SUMS
SH
    chmod +x "$DST/join.sh"
    cd "$REPO"
    git add -f release/   # release/ is git-ignored so it can't be committed by accident
    git commit -q -m "Release $TAG"
    echo
    echo "Committed release/ ($TAG). Push this branch to the PRIVATE remote; the 'Publish APK release'"
    echo "workflow then creates the GitHub Release. Afterwards remove release/ in a follow-up commit."
    ;;
esac
