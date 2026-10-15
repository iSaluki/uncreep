# Creep catalogue

What to look for in Phase 3. Each category lists **signals** (where `uncreep analyse` points
you), **how to confirm** in code, and the **usual removal**. Severity guide:

- **Critical:** covert collection of sensitive data, or data about people or sites outside the app.
- **High:** profiling or tracking the user wouldn't reasonably expect, or a dark pattern that undermines consent.
- **Medium:** manipulative engagement design, or tracking with a visible switch.
- **Low:** nags and annoyances.

This list is not exhaustive. Real-world examples of most categories in popular apps are documented in
[iSaluki/algorithmresearch](https://github.com/iSaluki/algorithmresearch/blob/main/REPORT.md).

---

## A. Data collection and surveillance

| # | Category | Signals | Confirm by | Usual removal |
|---|---|---|---|---|
| A1 | **Location beyond the feature** (background location, Wi-Fi BSSID, cell-tower or Bluetooth scans bundled with GPS, periodic location uploads) | `ACCESS_*_LOCATION`, `ACCESS_BACKGROUND_LOCATION`, `NEARBY_WIFI_DEVICES`, `BLUETOOTH_SCAN`; scan `location`, `wifi_bt_cell_scan` | find who calls the location APIs, and whether results go to a feature or into an upload or analytics payload; check scheduling (workers, alarms) | remove the permissions (the app must already cope with denial); stub the collector or uploader; make "is location enabled" return false |
| A2 | **Contact / address-book upload** | `READ_CONTACTS`, `GET_ACCOUNTS`; scan `contacts`; strings like "find friends" | is it a one-off on request, or continuous and background? Is the hash salted? | remove the permissions; stub the upload worker or scheduler |
| A3 | **Installed-app profiling** | `QUERY_ALL_PACKAGES`; long `<queries>` package lists, bare `MAIN` intent query; scan `installed_apps` | where package lists or "is X installed" results go: analytics, ads, risk scoring? | remove `QUERY_ALL_PACKAGES` and profiling `<queries>` entries (keep ones a feature needs, e.g. share targets); stub the detector |
| A4 | **Device fingerprinting / identifiers** | scan `device_ids`, `device_fingerprint`, `root_emulator_checks`, `accounts`; `READ_PHONE_STATE` / `READ_PHONE_NUMBERS` | what is collected (Android ID, SIM, IMEI, build props, keyboards, accessibility services, sensors) and where it is sent | remove the phone permissions; stub the collector so it returns empty or default values. **Leave login and anti-fraud checks unless the user explicitly accepts the risk** |
| A5 | **Advertising ID & attribution** | `AD_ID`, `ACCESS_ADSERVICES_*`, install-referrer permission; trackers such as AppsFlyer, Adjust, Branch, Singular, Kochava | where the ad ID and referrer are read and sent | remove `AD_ID` and AdServices permissions (the system then returns a zeroed ID); stub attribution SDK initialisation |
| A6 | **Third-party analytics / tracker SDKs** | `trackers.json`; scan `sdk_init_calls`, `analytics_events`; meta-data like `*_collection_enabled`, `AutoInitEnabled`; startup providers | which SDKs actually start (an Application `onCreate`, androidx.startup, an `InitProvider`) | flip the SDK's own off-switch in meta-data where it exists; remove its auto-init provider or androidx.startup entry; stub the init call or the app's analytics wrapper |
| A7 | **First-party event logging / telemetry** | scan `analytics_events`; a central logger class with many callers | find the sink every event funnels into | stub the sink (one patch disables everything); keep crash reporting if the user wants it |
| A8 | **Clipboard reading** | scan `clipboard` | a primary-clip listener, or reads with no user paste action | stub the listener or read |
| A9 | **Media / camera-roll scanning** | `READ_MEDIA_*`, `ACCESS_MEDIA_LOCATION`; scan `media_scanning`, `screenshot_detection` | background indexing, EXIF GPS extraction, face detection, screenshot reporting | remove `ACCESS_MEDIA_LOCATION`; stub the indexer or force its setting off |
| A10 | **Microphone / camera / sensors in the background** | `RECORD_AUDIO`, `CAMERA`, sensors; scan `audio_camera`, `sensors` | anything not tied to a visible capture UI | stub the background path; remove the permission only if no wanted feature needs it |
| A11 | **Monitoring other sites in an in-app browser** | scan `webview_js_injection`, `webview_cookies`; JS files in assets | `evaluateJavascript` / `addJavascriptInterface` on third-party pages: pixels, form or keystroke capture, tracking scripts | send links to the user's own browser (stub the in-app browser launch or redirect it); or stub the injection hooks |
| A12 | **Cross-app identity sharing** | exported providers or receivers with ID-like names; custom permissions from the same publisher; `<queries>` for sibling apps | what another app can pull out | `unexport` the components; remove the sibling-app queries |
| A13 | **Background persistence for tracking** | `RECEIVE_BOOT_COMPLETED`; receivers for connectivity, Bluetooth, unlock or package events; scan `boot_persistence` | whether the trigger's work is tracking rather than something the user needs (sync, alarms) | stub the receiver's `onReceive` or the worker it schedules; unexport it |
| A14 | **Health, finance, children** | scan `health`, `minors_age`; age-estimation models in assets | sensitive-category inference or upload | stub the model or upload; flag Critical |

## B. Dark patterns and manipulation

| # | Category | Signals | Confirm by | Usual removal |
|---|---|---|---|---|
| B1 | **Consent assumed or pre-granted** | scan `consent_defaults`; CMP SDKs; defaults of `true` for ad or analytics storage | what happens before or without a consent choice | force consent getters to "denied", or stub tracking regardless of consent |
| B2 | **Confirmshaming / hidden decline / repeated asks** | strings: `confirmshaming_copy`, `nagging_copy`; scan `notification_nags` | dialogs whose "no" is hidden, guilt-worded or followed by "are you sure?"; re-prompt timers | stub the prompt's "should show" check to false; set re-prompt counters to "done" |
| B3 | **Endless feeds and autoplay** | scan `infinite_autoplay`; pagination or "load more" classes | auto-advance, infinite pagination in short-video feeds | stub the next-page fetch or auto-advance; remove the tab or entry point (user's choice) |
| B4 | **Streaks, loss aversion, guilt notifications** | scan `streaks`, `reengagement`; strings `loss_aversion_copy`, `guilt_copy` | push or notification scheduling aimed at lapsed users; streak-loss warnings | stub the scheduler or the re-engagement notification builder |
| B5 | **Fake urgency** | scan `urgency_countdown`; strings `urgency_copy` | client-side timers that reset, or "only X left" with no source | stub the countdown or banner |
| B6 | **Rating and review nags** | scan `rating_prompts` | review prompts triggered by engagement heuristics | stub the "should prompt" check |
| B7 | **Upsell interruptions** | strings `subscription_copy`; full-screen interstitials | upsell screens on launch or after actions | stub the "should show" check. **Never unlock paid features** |
| B8 | **Hard-to-find opt-outs / defaults on** | settings defaults in code; remote-config defaults | privacy settings defaulting to on, or reverting | force the getter to the private value |
| B9 | **Ads in unexpected places** | scan `ads`; sponsored or "promoted" units | ads in inboxes, chats or AI answers | user's call: high risk of breaching the terms of service. Stub the ad-unit loader if chosen |
| B10 | **Server-switchable features** | scan `remote_config_flags` | which flags gate the creepy paths | stub the flag getter to the safe value so a server can't switch it back on |

## C. Usually leave alone (mention, don't remove by default)

- Crash reporting with no identifiers. Useful to the developer, low privacy cost.
- Security: TLS, certificate pinning, encryption, authentication, integrity checks. **Never weaken these.**
  Integrity or attestation checks (Play Integrity, SafetyNet) may *fail* on a re-signed app, which is
  a known limitation, not something to patch around without the user's informed choice.
- Push notifications themselves (the user can turn them off in Android settings), unless the content
  is manipulative (B4).
- Anything a feature the user wants needs.

## Reporting checklist (per finding)

- [ ] confirmed in code (trigger → sink), not just a scan hit
- [ ] gated by a server flag? which default?
- [ ] what data, when, to where
- [ ] proposed removal: manifest and/or code, with exact targets
- [ ] what the user loses, and the risk of breakage
