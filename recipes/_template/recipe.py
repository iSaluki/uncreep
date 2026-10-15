"""uncreep recipe for <App name> <version> (<package>).

Copy this folder to recipes/<package>/ (`./uncreep new-recipe <package>` does it and fills in
the pins), then write one block per feature the user chose to remove. Keep every change tied to
an entry in FINDINGS.md, e.g. "# F3: contact upload".

Strategy, in order of preference (see docs/patching-guide.md):
  1. remove the capability in the manifest (permission, <queries> entry, exported flag);
  2. stub the code path (method returns immediately / returns "off");
  3. only then reach for bigger rewrites or helper classes in ./smali/.

Every helper raises if its target isn't found exactly once, so a recipe can't silently do
nothing on the wrong build.
"""

from pathlib import Path

from patchkit.manifest import Manifest
from patchkit.smali import (find_classes_with_string, list_methods, prepend_to_method,  # noqa: F401
                            replace_in_method, set_method_body, stub_method)

# -- Pins: the exact build this recipe was written for ------------------------------------------
PACKAGE = "com.example.app"
VERSION = "1.2.3"
BASE_SHA256 = "0000000000000000000000000000000000000000000000000000000000000000"
SIGNER_SHA256 = None  # original signing cert SHA-256 from workspace/<package>/input/IDENTITY.json
OUTPUT_NAME = "example-uncreeped"  # out/<OUTPUT_NAME>.apk


def patch_manifest(m: Manifest):
    # F1: example: location tracking
    # m.remove_permissions({"android.permission.ACCESS_FINE_LOCATION",
    #                       "android.permission.ACCESS_COARSE_LOCATION"}, why="[F1]")
    # F2: example: installed-app profiling
    # m.remove_permissions({"android.permission.QUERY_ALL_PACKAGES"}, why="[F2]")
    # m.remove_query_packages({"com.other.app"}, why="[F2]")
    # m.remove_query_intents({("android.intent.action.MAIN", None)}, why="[F2]")
    # F3: example: identifiers handed to other apps
    # m.unexport({"com.example.IdProvider"}, why="[F3]")
    # F4: example: SDK switch in meta-data
    # m.set_meta_data_bool("firebase_analytics_collection_enabled", False, why="[F4]")
    pass


def patch_code(root: Path, log):
    def stub(cls, method, value=None, why=""):
        stub_method(root, cls, method, value)
        log(f"stub  {cls}->{method}  {why}")

    # F1: example: no last-known location
    # stub("com/example/location/Tracker", "getLastLocation()Landroid/location/Location;", "null", "[F1]")
    # F5: example: analytics sink drops every event
    # stub("com/example/analytics/EventLogger", "log(Ljava/lang/String;Ljava/util/Map;)V", why="[F5]")
    # F6: example: a feature flag reads as off
    # stub("com/example/flags/Flags", "isUpsellEnabled()Z", False, "[F6]")
    pass
