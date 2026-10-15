#!/usr/bin/env python3
"""Sweep decompiled code and UI strings for privacy-relevant APIs, tracking SDK entry points and
dark-pattern identifiers/copy. Every hit is a lead to read, not a finding.

    scripts/scan_patterns.py workspace/<package>/jadx workspace/<package>/res workspace/<package>/analysis

The JADX folder may be a single tree (<dir>/sources) or per-DEX trees (<dir>/classesN/sources).
Library packages (androidx, kotlin, okhttp, ...) are excluded from code categories so hits mostly
reflect the app's own code; set SCAN_KEEP=com/google/foo/,... to re-include a prefix.
Writes scan.md and scan.json.
"""

import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CODE = {
    # --- data collection ---------------------------------------------------------------------
    "installed_apps": r"getInstalledPackages|getInstalledApplications|queryIntentActivities\(|getPackageInfo\(\"com\.",
    "usage_stats": r"UsageStatsManager|queryUsageStats|queryEvents\(|\"usagestats\"",
    "clipboard": r"getPrimaryClip\(|addPrimaryClipChangedListener|hasPrimaryClip\(",
    "contacts": r"ContactsContract",
    "call_log_sms": r"CallLog\.Calls|content://call_log|Telephony\.Sms|content://sms",
    "location": r"requestLocationUpdates|getLastKnownLocation|getCurrentLocation\(|FusedLocationProviderClient|addGeofences|getLastLocation\(",
    "wifi_bt_cell_scan": r"getScanResults\(|\.startScan\(|getBSSID\(|getSSID\(|BluetoothLeScanner|startDiscovery\(|getAllCellInfo|getNeighboringCellInfo",
    "device_ids": r"\"android_id\"|Settings\.Secure\.ANDROID_ID|getDeviceId\(|getImei\(|getMeid\(|getSubscriberId\(|getSimSerialNumber\(|getLine1Number\(|Build\.getSerial|getSerial\(\)",
    "advertising_id": r"AdvertisingIdClient|getAdvertisingIdInfo|AdIdManager|TopicsManager|MeasurementManager|AppSetIdClient",
    "install_referrer": r"InstallReferrerClient|getInstallReferrer",
    "accounts": r"AccountManager\.get\(|getAccountsByType|getAccounts\(\)",
    "sensors": r"TYPE_ACCELEROMETER|TYPE_GYROSCOPE|TYPE_MAGNETIC_FIELD|TYPE_PRESSURE|TYPE_LIGHT|TYPE_PROXIMITY|TYPE_STEP_COUNTER",
    "device_fingerprint": r"Build\.FINGERPRINT|getRunningAppProcesses|\"ro\.build|getSystemAvailableFeatures|getInstalledAccessibilityServiceList|KeyboardLayout|getEnabledInputMethodList",
    "root_emulator_checks": r"/system/xbin/su|\"/system/bin/su\"|ro\.kernel\.qemu|isEmulator|isRooted|Magisk|\bfrida|de\.robv\.android\.xposed|XposedBridge",
    "audio_camera": r"new AudioRecord\(|MediaRecorder\.AudioSource|SpeechRecognizer|CameraManager|openCamera\(",
    "screenshot_detection": r"ScreenCaptureCallback|registerScreenCaptureCallback|addScreenRecordingCallback|MediaStore\.Images.*observer|\"screenshot",
    "media_scanning": r"MediaStore\.Images\.Media\.EXTERNAL_CONTENT_URI|ExifInterface|TAG_GPS_LATITUDE|FaceDetector",
    "health": r"HealthConnectClient|ReadRecordsRequest|HeartRateRecord|StepsRecord",
    "text_capture": r"addTextChangedListener|onTextChanged|AccessibilityEvent\.getText",
    # --- web / injection ---------------------------------------------------------------------
    "webview_js_injection": r"evaluateJavascript\(|addJavascriptInterface|loadUrl\(\"javascript:",
    "webview_cookies": r"setAcceptThirdPartyCookies|CookieManager\.getInstance",
    # --- tracking SDK entry points (switch these off at the call site) -----------------------
    "sdk_init_calls": r"FirebaseAnalytics\.getInstance|setAnalyticsCollectionEnabled|AppsFlyerLib\.getInstance|Adjust\.(onCreate|initSdk)|Branch\.getAutoInstance|Amplitude\.getInstance|Mixpanel(API)?\.getInstance|Braze\.getInstance|FacebookSdk\.(sdkInitialize|fullyInitialize)|AppEventsLogger\.|com\.segment\.analytics|Sentry(Android)?\.init|FirebaseCrashlytics\.getInstance|Bugsnag\.start|Singular\.init|Kochava|OneSignal\.(init|initWithContext)|Leanplum|CleverTap|MoEngage|com\.iterable\.|Heap\.init|UXCam|Smartlook|LogRocket|FullStory|Clarity\.initialize",
    "consent_defaults": r"setConsent\(|ConsentStatus|AD_STORAGE|AD_USER_DATA|AD_PERSONALIZATION|ANALYTICS_STORAGE|\"gdpr|ccpa|tcString|IABTCF_|setDataProcessingOptions|setLimitedDataUse|tagForChildDirectedTreatment|setIsAgeRestrictedUser",
    "remote_config_flags": r"FirebaseRemoteConfig|MobileConfig|FeatureFlag|isFeatureEnabled|ExperimentManager|getExperiment",
    "analytics_events": r"logEvent\(|trackEvent\(|\.track\(\"|recordEvent\(|sendEvent\(",
    # --- persistence / background ------------------------------------------------------------
    "boot_persistence": r"BOOT_COMPLETED|MY_PACKAGE_REPLACED|setExactAndAllowWhileIdle|setAlarmClock|IGNORE_BATTERY_OPTIMIZATIONS|PeriodicWorkRequest",
    "full_screen_intent": r"setFullScreenIntent|USE_FULL_SCREEN_INTENT",
    # --- engagement / dark patterns (identifiers) --------------------------------------------
    "streaks": r"(?i)streak",
    "reengagement": r"(?i)re_?engag|resurrect|[^elo]lapsed|dormant|win_?back|churn",
    "notification_nags": r"(?i)push_?prime|soft_?prompt|pre_?prompt|notification_?permission_?(nudge|reprompt|upsell|reminder)|reprompt",
    "rating_prompts": r"ReviewManager|requestReviewFlow|launchReviewFlow|(?i)rate_?(us|app)_?(dialog|prompt)",
    "cancellation_retention": r"(?i)cancel(lation)?_?(flow|survey|offer)|retention_?offer|save_?offer|winback_?offer",
    "urgency_countdown": r"(?i)countdown|expires_?in|limited_?time|flash_?sale|time_?left|timer_?offer",
    "infinite_autoplay": r"(?i)autoplay|auto_?advance|infinite_?scroll|endless",
    "badges": r"ShortcutBadger|setNumber\(|badge_?count|setBadgeIconType",
    "minors_age": r"(?i)age_?(estimation|prediction|verification|gate)|predicted_?age|is_?teen|under_?13|underage",
    "ads": r"(?i)AdView|InterstitialAd|RewardedAd|NativeAd|AdLoader|AdRequest|MaxAd|IronSource|UnityAds|sponsored",
}
STRINGS = {
    "loss_aversion_copy": r"(?i)lose your|don.t lose|you.ll lose|before it.s too late|about to (end|expire|break|lose)|will (end|break|be lost)",
    "urgency_copy": r"(?i)last chance|limited time|ends in|expires|only today|hurry|act now|hours? left|minutes? left|ending soon|don.t miss",
    "confirmshaming_copy": r"(?i)no thanks|no, i|i don.t want|i.d rather|i.ll pass|i.m okay|lose my|give up",
    "nagging_copy": r"(?i)maybe later|not now|remind me|turn on notifications|enable notifications|allow notifications|rate us|enjoying",
    "social_pressure_copy": r"(?i)friends? (is|are) (waiting|watching)|is typing|seen by|viewed your|someone (viewed|liked|mentioned)",
    "guilt_copy": r"(?i)we miss|miss you|haven.t (seen|practiced|opened)|come back|you forgot|disappoint",
    "subscription_copy": r"(?i)free trial|cancel anytime|auto.?renew|renews|billed|subscription|premium",
    "data_copy": r"(?i)sync your contacts|upload your|find friends|personaliz|advertis|partners|share data|third.part|improve our",
}
LIB = ("androidx/", "android/support/", "kotlin/", "kotlinx/", "okhttp3/", "okio/", "retrofit2/", "com/google/",
       "io/reactivex", "com/squareup/", "dagger/", "javax/", "org/", "j$/", "com/bumptech/", "io/grpc/",
       "com/fasterxml/", "io/sentry/", "com/airbnb/lottie/", "coil/", "com/apollographql/")


def roots(jadx: Path):
    if (jadx / "sources").is_dir():
        return [("", jadx / "sources")]
    return [(d.name + ":", d / "sources") for d in sorted(jadx.iterdir()) if (d / "sources").is_dir()]


def rg(pattern, root: Path, globs):
    # Run inside root: rg anchors "dir/**" globs to the working directory, not to the search path.
    cmd = ["rg", "-n", "--no-heading", "-M", "260", "--max-columns-preview", "-e", pattern, "."]
    cmd += sum([["-g", g] for g in globs], [])
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=root).stdout.splitlines()
    return [l[2:] if l.startswith("./") else l for l in out]


def main(jadx, res, out_dir):
    jadx, res, out_dir = Path(jadx), Path(res), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = [k for k in os.environ.get("SCAN_KEEP", "").split(",") if k]
    globs = ["*.java"] + [f"!{l}**" for l in LIB if not any(k.startswith(l) for k in keep)]
    summary = {}
    md = [f"# Pattern scan: {jadx}", "", "Leads only. Read the code before calling anything a finding.", "",
          "## Code (library packages excluded)", ""]
    for cat, pat in CODE.items():
        lines = []
        for prefix, root in roots(jadx):
            lines += [prefix + l for l in rg(pat, root, globs)]
        files = collections.Counter(re.match(r"(?:classes\d*:)?[^:]+", l).group(0) for l in lines)
        summary[cat] = {"hits": len(lines), "files": len(files), "top_files": [f for f, _ in files.most_common(15)]}
        md += [f"### {cat}: {len(lines)} hits in {len(files)} files", ""]
        md += [f"- `{f}` ({c})" for f, c in files.most_common(15)]
        md += ["", "```"] + [l[:300] for l in lines[:15]] + ["```", ""]
    values = res / "res" / "values"
    if values.is_dir():
        md += ["## UI strings (default locale)", ""]
        for cat, pat in STRINGS.items():
            lines = rg(pat, values, ["strings.xml", "plurals.xml"])
            summary[cat] = {"hits": len(lines)}
            md += [f"### {cat}: {len(lines)} strings", "", "```"]
            md += [l[:300] for l in lines[:200]] + ["```", ""]
    else:
        md += ["(no decoded resources: UI string categories skipped)", ""]
    (out_dir / "scan.md").write_text("\n".join(md))
    (out_dir / "scan.json").write_text(json.dumps(summary, indent=1))
    busy = sorted(((v["hits"], k) for k, v in summary.items() if v["hits"]), reverse=True)
    print("scan: " + ", ".join(f"{k}={n}" for n, k in busy[:20]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
