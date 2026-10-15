"""Helpers for rewriting methods in apktool-generated smali.

All helpers take `root`, the apktool output directory (the one containing smali/, smali_classes2/,
...), and a class name written as a path: "com/example/Foo" or, for obfuscated code, "X/0Ab1".
Methods are identified by their exact smali signature: "name(args)ret", e.g.
"isTrackingEnabled(Landroid/content/Context;)Z".

Every helper fails loudly (PatchError) when its target is not found exactly once, so a recipe
written for one app version cannot silently do nothing on another.
"""

import re
from pathlib import Path


class PatchError(Exception):
    pass


# Every smali file rewritten by these helpers. The build reassembles only the DEX files that
# contain one of them; every other DEX file is copied from the original APK byte-for-byte.
TOUCHED: set[Path] = set()

_METHOD_RE = re.compile(r"^\.method (?P<mods>[^\n]*?)(?P<name>[\w<>$-]+)\((?P<args>[^)]*)\)(?P<ret>\S+)$")


def find_class(root: Path, cls: str) -> Path:
    """Return the smali file of class `cls` ('com/foo/Bar' or 'com.foo.Bar')."""
    rel = cls.replace(".", "/").removeprefix("L").removesuffix(";") + ".smali"
    hits = [d / rel for d in sorted(Path(root).glob("smali*")) if (d / rel).is_file()]
    if len(hits) != 1:
        raise PatchError(f"class {cls}: expected exactly one smali file, found {len(hits)}")
    return hits[0]


def list_methods(root: Path, cls: str) -> list[str]:
    """All method signatures of a class, as accepted by the other helpers."""
    out = []
    for line in find_class(root, cls).read_text().split("\n"):
        m = _METHOD_RE.match(line)
        if m:
            out.append(f"{m['name']}({m['args']}){m['ret']}")
    return out


def find_classes_with_string(root: Path, s: str) -> list[str]:
    """Classes whose smali contains the string constant `s` (const-string "s")."""
    needle = f'"{s}"'
    hits = []
    for d in sorted(Path(root).glob("smali*")):
        for p in d.rglob("*.smali"):
            if needle in p.read_text(errors="replace"):
                hits.append(str(p.relative_to(d))[:-6])
    return hits


def _split_sig(method: str):
    name, rest = method.split("(", 1)
    args, ret = rest.split(")", 1)
    return name, args, ret


def _stub_body(ret: str, value) -> list[str]:
    """Smali body that returns immediately.

    value, by return type:
      V            ignored
      Z B S C I    bool or int (default 0 / false)
      J            int (default 0);  F, D: always 0.0
      objects      "null" | "string:<text>" | "sget:<field ref>" (e.g. kotlin Unit.INSTANCE) |
                   "bool:true" / "bool:false" (java.lang.Boolean) |
                   "empty:list" / "empty:map" / "empty:set" (java.util.Collections)
    """
    if ret == "V":
        return ["    .locals 0", "", "    return-void"]
    if ret in ("Z", "B", "S", "C", "I"):
        v = int(bool(value)) if isinstance(value, bool) else int(value or 0)
        return ["    .locals 1", "", f"    const v0, {v:#x}", "", "    return v0"]
    if ret == "J":
        return ["    .locals 2", "", f"    const-wide v0, {int(value or 0):#x}L", "", "    return-wide v0"]
    if ret == "D":
        return ["    .locals 2", "", "    const-wide/16 v0, 0x0", "", "    return-wide v0"]
    if ret == "F":
        return ["    .locals 1", "", "    const/4 v0, 0x0", "", "    return v0"]
    if value is None or value == "null":
        return ["    .locals 1", "", "    const/4 v0, 0x0", "", "    return-object v0"]
    if not isinstance(value, str):
        raise PatchError(f"don't know how to stub a method returning {ret} with {value!r}")
    kind, _, arg = value.partition(":")
    if kind == "sget":
        return ["    .locals 1", "", f"    sget-object v0, {arg}", "", "    return-object v0"]
    if kind == "string":
        s = arg.replace("\\", "\\\\").replace('"', '\\"')
        return ["    .locals 1", "", f'    const-string v0, "{s}"', "", "    return-object v0"]
    if kind == "bool":
        f = "TRUE" if arg == "true" else "FALSE"
        return ["    .locals 1", "", f"    sget-object v0, Ljava/lang/Boolean;->{f}:Ljava/lang/Boolean;", "",
                "    return-object v0"]
    if kind == "empty":
        types = {"list": "Ljava/util/List;", "map": "Ljava/util/Map;", "set": "Ljava/util/Set;"}
        t = types[arg]
        return ["    .locals 1", "",
                f"    invoke-static {{}}, Ljava/util/Collections;->empty{arg.capitalize()}(){t}",
                "    move-result-object v0", "", "    return-object v0"]
    raise PatchError(f"unknown stub value {value!r}")


def _method_span(lines: list[str], cls: str, method: str) -> tuple[int, int, re.Match]:
    """(index of .method line, index of .end method line, match) for exactly one method."""
    m_name, m_args, m_ret = _split_sig(method)
    found = []
    for i, line in enumerate(lines):
        m = _METHOD_RE.match(line)
        if m and m["name"] == m_name and m["args"] == m_args and m["ret"] == m_ret:
            j = i + 1
            while lines[j].strip() != ".end method":
                j += 1
            found.append((i, j, m))
    if len(found) != 1:
        raise PatchError(f"{cls}->{method}: matched {len(found)} methods")
    return found[0]


def set_method_body(root: Path, cls: str, method: str, body) -> Path:
    """Replace the whole body of `method` with the given smali (a string or a list of lines).

    The body must start with its own `.locals N`. Parameter names and annotations are dropped
    together with the old body (harmless at runtime).
    """
    if isinstance(body, str):
        body = ["    " + l.strip() if l.strip() else "" for l in body.strip("\n").split("\n")]
    path = find_class(root, cls)
    lines = path.read_text().split("\n")
    i, j, m = _method_span(lines, cls, method)
    mods = f" {m['mods']} "
    if " abstract " in mods or " native " in mods:
        raise PatchError(f"{cls}->{method} has no body")
    lines[i + 1:j] = body
    path.write_text("\n".join(lines))
    TOUCHED.add(path)
    return path


def stub_method(root: Path, cls: str, method: str, value=None) -> Path:
    """Make `method` return immediately (see _stub_body for `value`).

    Constructors cannot be stubbed this way (they must call the superclass constructor); use
    set_method_body for those.
    """
    if method.startswith("<init>("):
        raise PatchError(f"{cls}->{method}: refusing to stub a constructor; use set_method_body")
    ret = method.rsplit(")", 1)[1]
    return set_method_body(root, cls, method, _stub_body(ret, value))


def replace_in_method(root: Path, cls: str, method: str, old: str, new: str, count: int = 1) -> Path:
    """Exact text replacement restricted to one method body; `old` must occur exactly `count` times."""
    path = find_class(root, cls)
    lines = path.read_text().split("\n")
    i, j, _ = _method_span(lines, cls, method)
    body = "\n".join(lines[i + 1:j])
    n = body.count(old)
    if n != count:
        raise PatchError(f"{cls}->{method}: expected {count} occurrence(s) of {old!r}, found {n}")
    lines[i + 1:j] = body.replace(old, new).split("\n")
    path.write_text("\n".join(lines))
    TOUCHED.add(path)
    return path


def prepend_to_method(root: Path, cls: str, method: str, code: str) -> Path:
    """Insert smali instructions before the first instruction of `method`.

    Use p-registers (parameters) or v-registers within the method's existing `.locals` count.
    Typical use: call a helper and return early, e.g.

        invoke-static {p0}, Luncreep/Helpers;->shouldBlock(Ljava/lang/Object;)Z
        move-result v0
        if-eqz v0, :uncreep_continue
        return-void
        :uncreep_continue
    """
    path = find_class(root, cls)
    lines = path.read_text().split("\n")
    i, j, _ = _method_span(lines, cls, method)
    k, in_block = i + 1, False
    while k < j:
        s = lines[k].strip()
        if in_block:
            in_block = not s.startswith((".end annotation", ".end param"))
        elif s.startswith(".annotation") or (s.startswith(".param") and k + 1 < j and
                                              lines[k + 1].strip().startswith(".annotation")):
            in_block = True
        elif s and not s.startswith((".locals", ".registers", ".param", ".end param", ".prologue")):
            break
        k += 1
    if k >= j:
        raise PatchError(f"{cls}->{method}: no instructions found")
    lines[k:k] = ["    " + l.strip() if l.strip() else "" for l in code.strip("\n").split("\n")] + [""]
    path.write_text("\n".join(lines))
    TOUCHED.add(path)
    return path
