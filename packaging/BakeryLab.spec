# Build from any working directory with: python -m PyInstaller packaging/BakeryLab.spec
# The resulting dist/BakeryLab folder is a complete portable Windows download.
from pathlib import Path

project = Path(SPECPATH).resolve().parent
a = Analysis(
    [str(project / 'desktop.py')],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(project / 'log.html'), '.'), (str(project / 'index.html'), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BakeryLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BakeryLab')
