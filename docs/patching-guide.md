# Patching guide

How `./uncreep build` works and how to write a recipe that survives contact with a real app.

## How the build works

1. **Pins.** The base APK's SHA-256 (and the original signer, if pinned) must match the recipe.
   Obfuscated names (`X/0Ab1`, `defpackage/aBc`) change with every release, so a recipe is valid for
   exactly one build.
2. **Disassemble code only.** `apktool d --no-res` turns each `classesN.dex` into `smali_classesN/`.
   Resources are *not* decoded. Many large apps' resources can't be recompiled, so
   `resources.arsc`, `res/`, assets and native libraries are copied byte-for-byte.
3. **Manifest:** edited *in its compiled (binary) form* by `patchkit/axml.py`. It can remove
   elements and flip existing boolean attributes. It can't add elements or attributes.
4. **Code:** your `patch_code()` edits smali through `patchkit/smali.py`.
5. **Helpers:** smali files in `recipes/<package>/smali/` become a **new** `classesN+1.dex`, so
   they never push an existing DEX over the 64K-method limit.
6. **Reassemble only touched DEX files**, check each with **D8** (rejects broken bytecode), and
   swap them into a copy of the original APK. Original signatures are dropped.
7. **zipalign** (16 KB pages) and **sign** base and splits with your key (`keystore/uncreep.jks`,
   created on first build). Then **merge** base and splits into one APK with APKEditor, which also
   removes the split requirement from the manifest.

## Writing a recipe

```python
# recipes/com.example.app/recipe.py
PACKAGE = "com.example.app"
VERSION = "1.2.3"
BASE_SHA256 = "…"          # from workspace/<pkg>/input/IDENTITY.json
SIGNER_SHA256 = "…"
OUTPUT_NAME = "example-uncreeped"

def patch_manifest(m):
    m.remove_permissions({"android.permission.READ_CONTACTS"}, why="[F1]")

def patch_code(root, log):
    stub_method(root, "com/example/contacts/UploadWorker", "doWork()Landroidx/work/ListenableWorker$Result;",
                "sget:Landroidx/work/ListenableWorker$Result;->…")  # see "Return values" below
```

### Manifest helpers (`patchkit.manifest.Manifest`)

| Method | Effect | Notes |
|---|---|---|
| `remove_permissions(names)` | drops `<uses-permission>` / `-sdk-23` | Safe for **runtime** permissions: the app must already handle denial. Removing *normal* permissions (e.g. `INTERNET`) can crash code that assumes them |
| `remove_query_packages(pkgs)` / `remove_query_intents({(action, scheme)})` | narrows package visibility | Android then hides those apps from this app |
| `unexport(names)` | `exported=false` | other apps can no longer reach the component; the app itself still can |
| `disable(names)` | `enabled=false` | the attribute must already exist; apps may re-enable components at runtime |
| `remove_components(names)` | deletes the component | riskiest: anything that starts it crashes. OK for SDK auto-init providers |
| `set_meta_data_bool(name, v)` / `remove_meta_data(names)` | SDK switches, androidx.startup initialisers | check the SDK honours the flag |

Every helper raises if a target is missing (pass `required=False` to downgrade to a warning).

### Code helpers (`patchkit.smali`)

| Function | Use |
|---|---|
| `list_methods(root, cls)` | exact signatures to copy into the recipe |
| `find_classes_with_string(root, s)` | locate obfuscated classes by a string constant (event names, URLs, keys) |
| `stub_method(root, cls, sig, value)` | method returns immediately |
| `set_method_body(root, cls, sig, smali)` | replace a body (must declare `.locals`) |
| `replace_in_method(root, cls, sig, old, new)` | precise edit inside one method |
| `prepend_to_method(root, cls, sig, smali)` | insert code at the start, e.g. an early return guarded by a helper |

#### Return values for `stub_method`

| Return type | `value` |
|---|---|
| `V` | (none) |
| `Z` / `I` / `J` … | `False`, `True`, `0`, `42` |
| object | `None` (null), `"string:text"`, `"bool:false"`, `"empty:list"` / `"empty:map"` / `"empty:set"`, `"sget:Lcom/foo/Bar;->FIELD:Lcom/foo/Bar;"` (e.g. Kotlin `Unit.INSTANCE`, an enum constant, `ListenableWorker.Result`) |

## Choosing patch points

- **Patch the sink, not every source.** If 40 events go through one logger, stub the logger.
- **Patch the decision, not the UI.** A `shouldShowX()` returning `false` is safer than removing a view.
- **Prefer the narrowest method** that still blocks the behaviour. Read its callers: does anything
  dereference its return value? Returning `null` where callers don't null-check will crash.
  Use an empty collection, a default object, or `false` instead.
- **Kotlin coroutines:** `suspend` functions take a trailing `Lkotlin/coroutines/Continuation;` and
  return `Ljava/lang/Object;`. Stubbing them to return `Unit.INSTANCE` (`sget:Lkotlin/Unit;->INSTANCE:Lkotlin/Unit;`,
  or the obfuscated equivalent) completes them immediately.
- **WorkManager workers:** make `doWork()` return `Result.success()`, or stop the work being enqueued.
- **Constructors** can't be stubbed (they must call `super`). Use `set_method_body` keeping the
  `invoke-direct … <init>` call and required field initialisation, or patch the caller.
- **Server flags:** stub the flag getter to the safe value so a remote switch can't turn it back on.
- **Belt and braces:** for important findings, remove the capability *and* stub the code.

## Smali essentials

```smali
.method public isTrackingEnabled()Z
    .locals 1                 # number of v-registers; parameters are p0 (this), p1, …
    const/4 v0, 0x0
    return v0
.end method
```

- `long`/`double` take two registers. `.locals` must cover every `vN` you use.
- Static methods have no `this`, so `p0` is the first argument.
- Labels must be unique within a method. Prefix yours (`:uncreep_skip`).
- D8 validation catches most mistakes. Fix them before shipping.

## When the dex-only approach isn't enough

- **Strings and layouts** (e.g. rewording confirmshaming copy) need resource changes. Try a full
  `apktool d` / `apktool b` round-trip in the workspace by hand. It works for many smaller apps but
  often fails for large ones. Prefer code-level fixes where possible.
- **React Native** (`assets/index.android.bundle`): plain JS bundles can be edited as text. Hermes
  bytecode needs a Hermes disassembler or assembler (out of scope for patchkit).
- **Flutter / native code:** patching `libapp.so` or other native libraries is out of scope. Limit
  changes to the manifest and Java/Kotlin layers.
