from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


backend = Path(SPECPATH)
datas = [
    (str(backend / "static"), "static"),
    (str(backend / "app" / "platform_options.json"), "app"),
] + collect_data_files("tzdata")

hiddenimports = [
    "app.main", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.websockets_sansio_impl", "uvicorn.lifespan.on",
    "uvicorn.lifespan.off", "AppKit", "Foundation", "objc",
] + collect_submodules("websockets.asyncio")

a = Analysis(
    [str(backend / "desktop.py")],
    pathex=[str(backend)], binaries=[], datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[
        "playwright", "pymysql", "cryptography", "pandas", "numpy", "matplotlib",
        "pytest", "unittest", "test", "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="FindBoss", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    argv_emulation=False, target_arch="arm64", codesign_identity=None,
    entitlements_file=None,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FindBoss")
app = BUNDLE(
    collection, name="FindBoss.app", icon=None,
    bundle_identifier="local.findboss.workbench",
    info_plist={
        "CFBundleName": "FindBoss", "CFBundleDisplayName": "FindBoss",
        "CFBundleShortVersionString": "1.0.0", "CFBundleVersion": "1",
        "LSUIElement": True, "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
)
