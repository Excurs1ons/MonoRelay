# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MonoRelay 单文件打包

打包策略：
- 将所有 Python 代码打包为单个 .exe
- config.yml、data/ 目录剥离到运行时目录
- frontend/index.html 打包进 exe（通过 _MEIPASS 访问）
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 收集所有 backend 子模块
hidden_imports = collect_submodules('backend')
hidden_imports += [
    'fastapi',
    'uvicorn',
    'httpx',
    'pydantic',
    'pydantic_settings',
    'yaml',
    'aiosqlite',
    'watchfiles',
    'multipart',
    'base64',
]

# 收集 frontend 静态文件
frontend_datas = collect_data_files('frontend', include_py_files=False)

a = Analysis(
    ['backend/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend', 'frontend'),
        ('config.yml.example', '.'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'http',
        'xml',
        'pydoc',
        'setuptools',
        'distutils',
        'test',
        'pip',
        'wheel',
        'jinja2',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MonoRelay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
