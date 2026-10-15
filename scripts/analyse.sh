#!/usr/bin/env bash
# Phases 2 and 3 (mechanical part): decompile the app and produce leads for the agent to read.
#
#   scripts/analyse.sh <package>
#
# Reads workspace/<package>/input/ and writes:
#   workspace/<package>/smali/          apktool smali (what recipes patch; grep it for patch points)
#   workspace/<package>/res/            decoded resources (strings, layouts) if apktool can decode them
#   workspace/<package>/jadx/classesN/  JADX Java per DEX file (what you read)
#   workspace/<package>/analysis/       manifest.md/json, trackers.json, scan.md/json, SUMMARY.md
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PKG="${1:?usage: scripts/analyse.sh <package>}"
WS="$REPO/workspace/$PKG"
A="$WS/analysis"
T="$REPO/tools"
BASE="$WS/input/base.apk"
[ -f "$BASE" ] || { echo "no $BASE: run ./uncreep acquire $PKG first" >&2; exit 1; }
mkdir -p "$A"

echo "== manifest"
python3 "$REPO/scripts/manifest_audit.py" "$BASE" "$A"

echo "== trackers"
python3 "$REPO/scripts/tracker_scan.py" "$A/trackers.json" "$WS"/input/*.apk || echo "tracker scan skipped"

echo "== smali (apktool)"
"$T/apktool" d --no-res -f -o "$WS/smali" "$BASE" >"$A/apktool-smali.log" 2>&1
echo "$(ls -d "$WS"/smali/smali* | wc -l) DEX file(s) disassembled"

echo "== resources (apktool)"
if "$T/apktool" d -s -f -o "$WS/res" "$BASE" >"$A/apktool-res.log" 2>&1; then
  echo "decoded"
else
  echo "resource decoding failed (see analysis/apktool-res.log); UI string scan will be skipped"
fi

echo "== decompile (JADX, one DEX at a time)"
mkdir -p "$WS/dex" "$WS/jadx"
unzip -q -o "$BASE" 'classes*.dex' -d "$WS/dex"
JOBS="${UNCREEP_JOBS:-$(( $(nproc) > 2 ? $(nproc) / 2 : 1 ))}"
export JAVA_OPTS="${JAVA_OPTS:--Xmx4g}"
decompile() {
  local dex=$1 out="$WS/jadx/$(basename "${1%.dex}")"
  [ -f "$out/.done" ] && return 0
  rm -rf "$out"
  "$T/jadx/bin/jadx" -j 2 --no-res --show-bad-code -d "$out" "$dex" >"$out.log" 2>&1 || true
  touch "$out/.done"
  echo "  $(basename "$dex") done"
}
export -f decompile; export WS T
ls "$WS"/dex/classes*.dex | xargs -P "$JOBS" -I{} bash -c 'decompile {}'

echo "== pattern scan"
python3 "$REPO/scripts/scan_patterns.py" "$WS/jadx" "$WS/res" "$A"

echo "== summary"
python3 "$REPO/scripts/summarise.py" "$PKG"
