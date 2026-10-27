#!/usr/bin/env bash
# 把休眠壁纸传到 Kindle 并通过 inspector 设置（Kindle 必须醒着且 KOReader 在运行）。
set -euo pipefail
cd "$(dirname "$0")"; K="$PWD/kssh.sh"
"$K" "mkdir -p /mnt/us/koreader/screensaver && cat > /mnt/us/koreader/screensaver/great-wave-pw3.png" < ../wallpaper/great-wave-pw3.png
echo "已上传。请在 KOReader：设置 → 屏幕 → 屏保 → 选择 'Show image' 并指向 /mnt/us/koreader/screensaver/great-wave-pw3.png"
