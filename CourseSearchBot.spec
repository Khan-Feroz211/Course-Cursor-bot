# CourseSearchBot.spec
# Build command:
#   Windows:  pyinstaller CourseSearchBot.spec
#   Mac:      pyinstaller CourseSearchBot.spec
#
# Output will be in: dist/CourseSearchBot/

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('config/settings.yaml', 'config'),
        ('ui', 'ui'),
    ],
    hiddenimports=[
        'sentence_transformers',
        'sentence_transformers.models',
        'faiss',
        'pdfplumber',
        'fpdf',
        'yaml',
        'numpy',
        'PIL',
        'sklearn',
        'sklearn.preprocessing',
        'huggingface_hub',
        'transformers',
        'torch',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CourseSearchBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window — clean app experience
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='ui/icon.ico',    # Uncomment and add icon file to enable
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CourseSearchBot',
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='CourseSearchBot.app',
        # icon='ui/icon.icns',   # Uncomment for Mac icon
        bundle_identifier='com.coursesearchbot.app',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '2.0.0',
        },
    )
