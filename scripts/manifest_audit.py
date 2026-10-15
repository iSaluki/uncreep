#!/usr/bin/env python3
"""Summarise the privacy-relevant parts of a manifest: permissions (flagging dangerous ones),
<queries> package visibility, exported components, boot/background hooks and SDK meta-data.

    scripts/manifest_audit.py workspace/<package>/input/base.apk workspace/<package>/analysis

Writes manifest.json and manifest.md into the output folder.
"""

import json
import re
import sys
from pathlib import Path

from androguard.core.api_specific_resources import load_permissions
from androguard.core.apk import APK
from androguard.util import set_log

set_log("ERROR")
NS = "{http://schemas.android.com/apk/res/android}"

# Permissions that matter for privacy even though Android doesn't class them as "dangerous".
NOTABLE = {
    "com.google.android.gms.permission.AD_ID": "advertising ID",
    "android.permission.ACCESS_ADSERVICES_AD_ID": "Privacy Sandbox ad ID",
    "android.permission.ACCESS_ADSERVICES_ATTRIBUTION": "Privacy Sandbox attribution",
    "android.permission.ACCESS_ADSERVICES_TOPICS": "Privacy Sandbox topics",
    "android.permission.QUERY_ALL_PACKAGES": "sees every installed app",
    "android.permission.PACKAGE_USAGE_STATS": "app-usage history (if granted in settings)",
    "android.permission.RECEIVE_BOOT_COMPLETED": "starts at boot",
    "android.permission.SYSTEM_ALERT_WINDOW": "draws over other apps",
    "android.permission.USE_FULL_SCREEN_INTENT": "full-screen notifications",
    "android.permission.SCHEDULE_EXACT_ALARM": "exact alarms",
    "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS": "asks to bypass battery limits",
    "com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE": "install referrer (attribution)",
    "android.permission.BLUETOOTH_SCAN": "Bluetooth scanning",
    "android.permission.NEARBY_WIFI_DEVICES": "Wi-Fi scanning",
    "android.permission.ACCESS_WIFI_STATE": "Wi-Fi network details",
    "android.permission.GET_ACCOUNTS": "device accounts",
    "android.permission.READ_PHONE_NUMBERS": "phone number",
    "android.permission.HIGH_SAMPLING_RATE_SENSORS": "high-rate motion sensors",
    "android.permission.ACTIVITY_RECOGNITION": "physical activity",
}


def main(apk_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    a = APK(apk_path)
    m = a.get_android_manifest_xml()
    perms = sorted(a.get_permissions())
    sdk23 = sorted({e.get(NS + "name") for e in m.findall("uses-permission-sdk-23")} - set(perms))
    platform = load_permissions(34)
    allp = perms + sdk23
    dangerous = [p for p in allp if "dangerous" in str(platform.get(p, {}).get("protectionLevel", ""))]
    custom = [p for p in allp if not p.startswith("android.permission.") and p not in NOTABLE]

    queries = {"packages": [], "intents": [], "providers": []}
    for q in m.findall("queries"):
        queries["packages"] += [p.get(NS + "name") for p in q.findall("package")]
        for i in q.findall("intent"):
            queries["intents"].append({"actions": [x.get(NS + "name") for x in i.findall("action")],
                                       "data": [{k.replace(NS, ""): v for k, v in x.attrib.items()} for x in i.findall("data")]})
        queries["providers"] += [p.get(NS + "authorities") for p in q.findall("provider")]

    app = m.find("application")
    meta = {x.get(NS + "name"): x.get(NS + "value") or x.get(NS + "resource") for x in app.iter("meta-data")}
    # Redact embedded keys/tokens so audits can be shared.
    meta = {k: ("[redacted]" if re.search(r"token|apikey|api_key|secret|client_?key|client_?id", k or "", re.I)
                and v and not str(v).startswith("@") else v) for k, v in meta.items()}

    def comps(tag):
        res = []
        for c in app.findall(tag):
            actions = [x.get(NS + "name") for f in c.findall("intent-filter") for x in f.findall("action")]
            exp = c.get(NS + "exported")
            res.append({"tag": tag, "name": c.get(NS + "name"), "exported": exp,
                        "effectively_exported": exp == "true" or (exp is None and bool(actions)),
                        "enabled": c.get(NS + "enabled"), "actions": actions,
                        "permission": c.get(NS + "permission"),
                        "foregroundServiceType": c.get(NS + "foregroundServiceType")})
        return res

    components = sum((comps(t) for t in ("activity", "activity-alias", "service", "receiver", "provider")), [])
    data = {"package": a.get_package(), "version": a.get_androidversion_name(),
            "permissions": perms, "permissions_sdk23": sdk23, "dangerous_permissions": dangerous,
            "notable_permissions": {p: NOTABLE[p] for p in allp if p in NOTABLE}, "custom_permissions": custom,
            "queries": queries, "meta_data": meta, "components": components}
    (out_dir / "manifest.json").write_text(json.dumps(data, indent=1))

    exported = [c for c in components if c["effectively_exported"] and c["tag"] != "activity"]
    boot = [c for c in components if any(re.search(r"BOOT_COMPLETED|MY_PACKAGE_REPLACED|USER_PRESENT|CONNECTIVITY|"
                                                   r"bluetooth|PACKAGE_ADDED|PACKAGE_REMOVED|INSTALL_REFERRER", x or "")
                                         for x in c["actions"])]
    md = [f"# Manifest audit: {data['package']} {data['version']}", "",
          f"## Dangerous (runtime) permissions ({len(dangerous)})", ""] + [f"- `{p}`" for p in dangerous] + [
          "", f"## Other notable permissions ({len(data['notable_permissions'])})", ""] + [
          f"- `{p}`: {d}" for p, d in data["notable_permissions"].items()] + [
          "", f"## Custom / third-party permissions ({len(custom)})", ""] + [f"- `{p}`" for p in custom] + [
          "", f"## Package visibility (`<queries>`): {len(queries['packages'])} packages, "
              f"{len(queries['intents'])} intents, {len(queries['providers'])} providers", "",
          "An app normally only needs to see apps it integrates with. Long lists of unrelated packages, a bare "
          "`MAIN` intent or `QUERY_ALL_PACKAGES` suggest installed-app profiling.", ""] + [
          f"- package `{p}`" for p in queries["packages"]] + [
          f"- intent {i['actions']} {i['data'] or ''}" for i in queries["intents"]] + [
          f"- provider `{p}`" for p in queries["providers"]] + [
          "", f"## Exported services/receivers/providers ({len(exported)})", "",
          "Reachable by other apps (e.g. the publisher's other apps pulling identifiers).", ""] + [
          f"- {c['tag']} `{c['name']}` actions={c['actions']} permission={c['permission']}" for c in exported] + [
          "", f"## Background triggers ({len(boot)})", ""] + [
          f"- {c['tag']} `{c['name']}` on {c['actions']}" for c in boot] + [
          "", f"## Meta-data ({len(meta)})", "", "SDK switches often live here (e.g. `*_collection_enabled`, "
          "`AutoInitEnabled`, `AdvertiserIDCollectionEnabled`).", ""] + [
          f"- `{k}` = `{v}`" for k, v in meta.items()]
    (out_dir / "manifest.md").write_text("\n".join(md) + "\n")
    print(f"manifest: {len(allp)} permissions ({len(dangerous)} dangerous), {len(queries['packages'])} queried packages, "
          f"{len(exported)} exported non-activity components, {len(boot)} background triggers")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
