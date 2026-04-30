#!/bin/bash
# 本地打包 lianzai-export 为 macOS .dmg
# 输出到项目根目录：lianzai_export_<version>_macos.dmg

set -e
cd "$(dirname "$0")"

VERSION="1.5"
APP_NAME="轻想连载导出"
DMG_NAME="lianzai_export_${VERSION}_macos.dmg"

# 在 /tmp 下 build，避免 exfat 盘的 symlink 限制
WORK_DIR="/tmp/lzx-build"
DIST_DIR="/tmp/lzx-dist"

PY=/opt/homebrew/bin/python3.11
PYINSTALLER=/opt/homebrew/bin/pyinstaller
CREATE_DMG=/opt/homebrew/bin/create-dmg

echo "▸ 清理旧产物"
rm -rf "$WORK_DIR" "$DIST_DIR" "$DMG_NAME"

echo "▸ PyInstaller 打包"
"$PYINSTALLER" \
  --windowed \
  --name "$APP_NAME" \
  --icon "AppIcon.png" \
  --workpath "$WORK_DIR" \
  --distpath "$DIST_DIR" \
  --noconfirm \
  main.py

# 防止 create-dmg 把 PyInstaller 同名目录也打进 dmg（参考 e1fcc1a 提交）
rm -rf "$DIST_DIR/$APP_NAME"

echo "▸ create-dmg 生成磁盘镜像"
"$CREATE_DMG" \
  --volname "$APP_NAME" \
  --window-size 660 400 \
  --icon-size 100 \
  --icon "${APP_NAME}.app" 180 170 \
  --app-drop-link 480 170 \
  --hide-extension "${APP_NAME}.app" \
  "$DMG_NAME" \
  "$DIST_DIR/${APP_NAME}.app"

echo
echo "✓ 完成：$(pwd)/$DMG_NAME"
ls -lh "$DMG_NAME"
