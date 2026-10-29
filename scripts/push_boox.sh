#!/usr/bin/env bash
# 把书推到 BOOX(安卓)的 /sdcard/Books,经 adb(设备上要开「USB 调试模式」:应用 → 右上角 → 应用管理)。
# 用法: push_boox.sh 书1.epub [书2.pdf ...]      默认目标目录 /sdcard/Books,可用 BOOX_DIR 覆盖
# 文件名保持不变——云端进度按 md5(文件名) 匹配,同一本书在 Kindle / BOOX / 电脑上文件名必须一致。
set -euo pipefail
[ $# -ge 1 ] || { echo "用法: $0 <文件...>"; exit 1; }
DEST=${BOOX_DIR:-/sdcard/Books}
# 自动挑 BOOX(多设备时 adb 需要 -s;本机常有离线模拟器残留)
SERIAL=${ANDROID_SERIAL:-$(adb devices -l | awk '/device:BOOX|product:BOOX/{print $1; exit}')}
[ -n "$SERIAL" ] || { echo "没找到 BOOX:检查数据线和「USB 调试模式」"; exit 1; }
adb -s "$SERIAL" shell mkdir -p "$DEST"
for f in "$@"; do
  [ -f "$f" ] || { echo "跳过(不存在): $f"; continue; }
  adb -s "$SERIAL" push "$f" "$DEST/$(basename "$f")" | tail -1
done
echo "已推到 $SERIAL:$DEST"
