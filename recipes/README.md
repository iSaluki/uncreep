# Recipes

One folder per app, named after its package: `recipes/<package>/`.

| File | Required | Contents |
|---|---|---|
| `recipe.py` | yes | pins (`PACKAGE`, `VERSION`, `BASE_SHA256`, optional `SIGNER_SHA256`, `OUTPUT_NAME`), `patch_manifest(m)` and `patch_code(root, log)` |
| `FINDINGS.md` | yes | what was found, what the user chose, what was removed (see `docs/findings-template.md`) |
| `smali/` | no | helper classes added to the app as a new DEX file |

Start one with `./uncreep new-recipe <package>` after `./uncreep acquire <package>`. It copies
`_template/` and fills in the pins.

A recipe applies to **one exact build**. For a new app version, analyse again and update the pins and
patch points.

**Recipes must not contain the app's code:** no APKs, no DEX, no decompiled sources, no copied
methods. Only your patch logic and the identifiers needed to find the code it changes.
This public repository ships only `_template/`. Keep your own recipes in your private copy (see
`docs/delivery.md`).
