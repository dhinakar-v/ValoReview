# PyInstaller spec for the desktop app's Python sidecar.
#
#     uv run pyinstaller desktop/packaging/vrf-desktop.spec --noconfirm
#
# Writes desktop/packaging/dist/valoreview-backend/, a onedir tree holding
# valoreview-backend.exe.  The Tauri shell ships that folder as a bundle
# resource and spawns it; see desktop/README.md.
#
# Onedir and not onefile.  A onefile build re-extracts the whole ~55 MB tree
# into %TEMP% on every launch, which costs seconds before the port opens and is
# the shape antivirus heuristics dislike most.  The installer already puts files
# on disk, so there is nothing to gain by pretending otherwise.
#
# Three things here are load-bearing and easy to get wrong:
#
#   * `pathex` names libraries/ and scripts/.  libraries/ is this project's
#     source *root*, not a package -- pyproject.toml maps its contents onto the
#     install root -- and scripts/ is not installed at all, so an analysis that
#     did not name both would not find `vrfserve` or `vrf_serve`.
#   * uvicorn loads its protocol, lifespan and loop implementations **by
#     string**, so no static analysis finds them.  Missing, the server imports
#     fine and then fails at bind.
#   * tkinter is excluded.  Pillow's hook pulls it in, which drags ~10 MB of
#     Tcl/Tk into a project whose interface is a browser and which draws no
#     widget anywhere.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]

hidden = [
    # Selected by name at run time from uvicorn.config's LOOP_SETUPS /
    # HTTP_PROTOCOLS / LIFESPAN tables.
    *collect_submodules("uvicorn.protocols"),
    *collect_submodules("uvicorn.lifespan"),
    *collect_submodules("uvicorn.loops"),
    # pydantic v2's validation core is a compiled extension reached through
    # pydantic._internal; vrfserve.schema imports pydantic directly.
    "pydantic.deprecated.decorator",
]

analysis = Analysis(
    [str(ROOT / "scripts" / "vrf_desktop.py")],
    pathex=[str(ROOT / "libraries"), str(ROOT / "scripts")],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "_tkinter",
        "PIL.ImageTk",
        # Dev tools. Nothing the sidecar runs imports them, and pytest in
        # particular pulls in a large tree.
        "pytest",
        "_pytest",
        "ruff",
        "httpx2",
        "IPython",
        "matplotlib",
        "numpy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="valoreview-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A console subsystem binary, deliberately.  The shell spawns it with
    # CREATE_NO_WINDOW so nothing is shown, and reads its stdout: the startup
    # lines (`replays`, `art`, `decoder`, `serving`) are what the splash screen
    # turns into progress, and a windowed build would have nowhere to write
    # them.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="valoreview-backend",
)
