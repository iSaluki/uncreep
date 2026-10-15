"""High-level edits of a compiled (binary) AndroidManifest.xml.

Every method fails loudly when a target is missing, unless `required=False`, so a recipe
pinned to one app version can't quietly stop working on another.
"""

from .axml import AXML, TYPE_INT_BOOLEAN


class ManifestError(Exception):
    pass


COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")


class Manifest:
    def __init__(self, data: bytes, log=print):
        self.doc = AXML(data)
        self.root = self.doc.root
        self.app = next(self.root.iter("application"))
        self.log = log

    @property
    def package(self):
        return self.root.get("package")

    def to_bytes(self) -> bytes:
        return self.doc.to_bytes()

    # -- lookups ------------------------------------------------------------------------------
    def permissions(self) -> list[str]:
        return [el.get("name") for el in self.root.children
                if el.tag in ("uses-permission", "uses-permission-sdk-23")]

    def components(self, tag=None):
        return [el for el in self.app.children if el.tag in COMPONENT_TAGS and (tag is None or el.tag == tag)]

    def component(self, name: str):
        hits = [el for el in self.components() if el.get("name") == name]
        if len(hits) != 1:
            raise ManifestError(f"component {name}: found {len(hits)}")
        return hits[0]

    # -- edits --------------------------------------------------------------------------------
    def remove_permissions(self, names, required=True, why=""):
        """Remove <uses-permission> (and -sdk-23) entries. Removing a runtime permission is the same
        as the user permanently denying it, which apps must already handle."""
        names = set(names)
        seen = set()
        for el in list(self.root.children):
            if el.tag in ("uses-permission", "uses-permission-sdk-23") and el.get("name") in names:
                seen.add(el.get("name"))
                self.doc.remove(el)
        self._check(names - seen, "permissions", required)
        self.log(f"manifest: removed {len(seen)} permission(s) {why}")

    def remove_query_packages(self, packages, required=True, why=""):
        """Remove <queries><package name=…/> entries, hiding those apps from this app."""
        packages = set(packages)
        seen = set()
        for q in [el for el in self.root.children if el.tag == "queries"]:
            for el in list(q.children):
                if el.tag == "package" and el.get("name") in packages:
                    seen.add(el.get("name"))
                    self.doc.remove(el)
        self._check(packages - seen, "<queries> packages", required)
        self.log(f"manifest: removed {len(seen)} <queries> package(s) {why}")

    def remove_query_intents(self, keys, required=True, why=""):
        """Remove <queries><intent> entries identified by (action, data scheme or None)."""
        keys = set(keys)
        seen = set()
        for q in [el for el in self.root.children if el.tag == "queries"]:
            for el in list(q.children):
                if el.tag != "intent":
                    continue
                actions = [c.get("name") for c in el.children if c.tag == "action"]
                schemes = [c.get("scheme") for c in el.children if c.tag == "data"]
                key = (actions[0] if actions else None, schemes[0] if schemes else None)
                if len(actions) == 1 and len(schemes) <= 1 and key in keys:
                    seen.add(key)
                    self.doc.remove(el)
        self._check(keys - seen, "<queries> intents", required)
        self.log(f"manifest: removed {len(seen)} <queries> intent(s) {why}")

    def unexport(self, names, required=True, why=""):
        """Set android:exported=false so no other app can start or bind the component.
        The attribute must already exist (it does for any component with an intent filter
        when targetSdk >= 31)."""
        names = set(names)
        done = set()
        for el in self.components():
            if el.get("name") in names:
                a = el.attr("exported")
                if a is None:
                    if any(c.tag == "intent-filter" for c in el.children):  # implicitly exported (targetSdk < 31)
                        raise ManifestError(f"{el.get('name')}: no exported attribute to change")
                    done.add(el.get("name"))  # no filters, no attribute: already not exported
                    continue
                a.set_bool(False)
                done.add(el.get("name"))
        self._check(names - done, "components", required)
        self.log(f"manifest: un-exported {len(done)} component(s) {why}")

    def disable(self, names, required=True, why=""):
        """Set android:enabled=false (attribute must exist). Prefer stubbing code: an app may
        re-enable components at runtime via PackageManager."""
        names = set(names)
        done = set()
        for el in self.components():
            if el.get("name") in names:
                a = el.attr("enabled")
                if a is None:
                    raise ManifestError(f"{el.get('name')}: no enabled attribute to change; remove it or stub its code")
                a.set_bool(False)
                done.add(el.get("name"))
        self._check(names - done, "components", required)
        self.log(f"manifest: disabled {len(done)} component(s) {why}")

    def remove_components(self, names, required=True, why=""):
        """Delete components entirely. Riskiest option: code that starts/binds them will crash.
        Reasonable for SDK auto-init providers (e.g. an analytics SDK's InitProvider) whose only
        job is to start that SDK."""
        names = set(names)
        done = set()
        for el in self.components():
            if el.get("name") in names:
                done.add(el.get("name"))
                self.doc.remove(el)
        self._check(names - done, "components", required)
        self.log(f"manifest: removed {len(done)} component(s) {why}")

    def set_meta_data_bool(self, name, value: bool, required=True, why=""):
        """Flip an existing boolean <meta-data> under <application> (and under components), e.g.
        an SDK's 'collection enabled' flag."""
        hits = [el for el in self.app.iter("meta-data") if el.get("name") == name]
        if not hits:
            self._check({name}, "meta-data", required)
            return
        for el in hits:
            a = el.attr("value")
            if a is None or a.data_type != TYPE_INT_BOOLEAN:
                raise ManifestError(f"meta-data {name} is not a boolean value")
            a.set_bool(value)
        self.log(f"manifest: meta-data {name}={str(value).lower()} {why}")

    def remove_meta_data(self, names, required=True, why=""):
        """Remove <meta-data> entries (anywhere under <application>), e.g. an
        androidx.startup initializer for a tracking SDK."""
        names = set(names)
        done = set()
        for el in list(self.app.iter("meta-data")):
            if el.get("name") in names:
                done.add(el.get("name"))
                self.doc.remove(el)
        self._check(names - done, "meta-data", required)
        self.log(f"manifest: removed {len(done)} meta-data entr(y/ies) {why}")

    def _check(self, missing, what, required):
        if missing:
            msg = f"{what} not found: {sorted(map(str, missing))}"
            if required:
                raise ManifestError(msg)
            self.log("manifest: warning: " + msg)
