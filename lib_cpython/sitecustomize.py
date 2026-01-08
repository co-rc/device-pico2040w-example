import sys

# this file is referenced by ".venv/Lib/site-packages/device_pico2040w_example.pth"

if getattr(sys, "implementation", None) and sys.implementation.name == "cpython":
    print("Customizing sys.path for CPython")
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    lib = root / "lib"
    lib_cpython = root / "lib_cpython"

    paths = [str(root), str(lib), str(lib_cpython)]
    for path in reversed(paths):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
