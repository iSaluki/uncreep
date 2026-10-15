#!/usr/bin/env bash
# Installs everything uncreep needs into tools/ (pinned versions, checked by SHA-256 where the
# upstream file is immutable). Idempotent: safe to re-run in a fresh container.
#
# Needs on the host: Java 17+, Python 3.10+, curl, unzip, keytool, ripgrep (rg).
# Optional: Node.js/npm (for REA, the Reverse Engineer Anything MCP server).
#
#   tools/setup.sh            # core tools
#   tools/setup.sh --no-rea   # skip REA
set -euo pipefail
cd "$(dirname "$0")"

WITH_REA=1
[ "${1:-}" = "--no-rea" ] && WITH_REA=0

need() { command -v "$1" >/dev/null || { echo "missing required command: $1 ($2)" >&2; exit 1; }; }
need java "install a JDK 17+"
need python3 "install Python 3.10+"
need curl ""
need unzip ""
need keytool "comes with the JDK"
need rg "install ripgrep"

fetch() {  # url sha256 dest
  if [ ! -f "$3" ]; then curl -fL --retry 3 -o "$3.part" "$1" && mv "$3.part" "$3"; fi
  echo "$2  $3" | sha256sum -c --quiet - || { rm -f "$3"; echo "checksum mismatch for $3" >&2; exit 1; }
}

# apkeep (EFF): downloads APKs from APKPure, Google Play, F-Droid or Huawei AppGallery
fetch https://github.com/EFForg/apkeep/releases/download/1.1.0/apkeep-x86_64-unknown-linux-gnu \
  badd7ad9fa7d2f32abe01eaf33b7ff086361a95bbc000a33bf44b630d4bf2140 apkeep
chmod +x apkeep

# Apktool: smali disassembly / reassembly
fetch https://github.com/iBotPeaches/Apktool/releases/download/v2.12.1/apktool_2.12.1.jar \
  66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa apktool.jar

# JADX: Java decompiler, for reading the code
if [ ! -x jadx/bin/jadx ]; then
  fetch https://github.com/skylot/jadx/releases/download/v1.5.3/jadx-1.5.3.zip \
    8280f3799c0273fe797a2bcd90258c943e451fd195f13d05400de5e6451d15ec jadx.zip
  rm -rf jadx && unzip -q jadx.zip -d jadx && rm jadx.zip && chmod +x jadx/bin/*
fi

# Android SDK build-tools 35: zipalign, apksigner, aapt2, d8
if [ ! -x build-tools/apksigner ]; then
  fetch https://dl.google.com/android/repository/build-tools_r35_linux.zip \
    bd3a4966912eb8b30ed0d00b0cda6b6543b949d5ffe00bea54c04c81e1561d88 build-tools.zip
  rm -rf build-tools android-* && unzip -q build-tools.zip && mv android-* build-tools && rm build-tools.zip
fi

# APKEditor (REAndroid): merges a base APK and its splits into one installable APK
fetch https://github.com/REAndroid/APKEditor/releases/download/V1.4.5/APKEditor-1.4.5.jar \
  71999a1f28cf6b457aff17c139436349cd6ea30d75a0f9cd52f07bd52e21897b APKEditor.jar

# Exodus Privacy tracker signatures (a living list, so not pinned; refreshed weekly)
if [ ! -f exodus-trackers.json ] || [ -n "$(find exodus-trackers.json -mtime +7)" ]; then
  curl -fsSL --retry 3 -o exodus-trackers.json.part https://reports.exodus-privacy.eu.org/api/trackers \
    && mv exodus-trackers.json.part exodus-trackers.json \
    || echo "warning: could not fetch Exodus tracker list; tracker scan will be skipped" >&2
fi

# Python dependency for manifest parsing
python3 -c 'import androguard' 2>/dev/null \
  || python3 -m pip install --quiet -r ../requirements.txt 2>/dev/null \
  || python3 -m pip install --quiet --break-system-packages -r ../requirements.txt

# REA (Reverse Engineer Anything) + the headless JADX engine it drives. Optional.
if [ "$WITH_REA" = 1 ]; then
  if command -v npm >/dev/null; then
    fetch https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar \
      6e5eacf500b64292bfb73c49797c1958f6ee44646e43e868039ae7feb573ff75 jadx-headless-mcp.jar
    command -v rea >/dev/null && [ "$(rea --version 2>/dev/null | tail -1)" = "6.4.0" ] \
      || npm install -g --silent rea-agents@6.4.0 \
      || echo "warning: REA install failed; the .mcp.json server will fall back to npx" >&2
  else
    echo "note: npm not found, skipping REA (optional)" >&2
  fi
fi

cat > apktool <<'SH'
#!/bin/sh
exec java ${APKTOOL_JAVA_OPTS:--Xmx6g} -jar "$(dirname "$(readlink -f "$0")")/apktool.jar" "$@"
SH
chmod +x apktool

echo "uncreep tools ready in $(pwd)"
