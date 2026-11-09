"""
Rewrites the few unresolved string literals that must EXIST (not merely be
referenced) inside a frozen build. Returns the number of files touched.

Run AFTER PyInstaller builds the onedir tree, with the tree root as argv[1]:

    python patch_frozen_paths.py <dist-root>

What it fixes
-------------
`core/gemini.py` resolves its asset root with `Path(__file__).resolve().parent.parent`.
When PyInstaller freezes the app, `core/gemini.py` is packed into the PYZ archive
and `__file__` points at a path that does not exist on disk (`<root>/core/gemini.py`).
`Path.resolve()` therefore keeps the literal string, and every `core/*` resource
(prompt.txt, face_model.obj) resolves to a nonexistent location -> the model is
called with an empty system prompt, silently, forever.

Every other module in the app guards this with `getattr(sys, "frozen", False)` and
falls back to `Path(sys.executable).parent`, which is correct and needs no patch.
`core/gemini.py` does not, so we rewrite that one call site to the same frozen-safe
form. The rewrite is deliberately narrow: it rewrites only the known call site and
only when the frozen-safe form is not already present, so a second run is a no-op.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The broken call site -> the same expression every other module already uses.
_NEEDLE = 'Path(__file__).resolve().parent.parent'
_FROZEN = 'Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent'


def _patch(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    if _FROZEN in text:          # already patched — idempotent
        return False
    if _NEEDLE not in text:
        return False
    try:
        path.write_text(text.replace(_NEEDLE, _FROZEN), encoding="utf-8")
    except Exception:
        return False
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_frozen_paths.py <dist-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    touched = []
    for py in root.rglob("*.py"):
        if _patch(py):
            touched.append(py.relative_to(root))
    for rel in touched:
        print(f"[patch] {rel}")
    print(f"[patch] {len(touched)} file(s) rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
