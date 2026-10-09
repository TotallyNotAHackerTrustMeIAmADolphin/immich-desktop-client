# -*- mode: python ; coding: utf-8 -*-
import os

# Windows version resource built from the VERSION file, so signed binaries carry product name and version.
_root = os.path.abspath(SPECPATH)
_version = open(os.path.join(_root, 'VERSION')).read().strip()
_parts = (_version.split('.') + ['0', '0', '0'])[:3] + ['0']
_tuple = ', '.join(_parts)
_info_path = os.path.join(_root, 'build', 'version_info.txt')
os.makedirs(os.path.dirname(_info_path), exist_ok=True)
with open(_info_path, 'w') as _f:
    _f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({_tuple}), prodvers=({_tuple}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Immich Desktop Client contributors'),
      StringStruct('FileDescription', 'Immich Desktop Client'),
      StringStruct('FileVersion', '{_version}'),
      StringStruct('InternalName', 'immich-desktop-client'),
      StringStruct('OriginalFilename', 'immich-desktop-client.exe'),
      StringStruct('ProductName', 'Immich Desktop Client'),
      StringStruct('ProductVersion', '{_version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")


a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='immich-desktop-client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/icon.ico'],
    version=_info_path,
)
