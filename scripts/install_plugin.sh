#!/usr/bin/env bash
# 电脑上运行：把 plugin/simpleui.koplugin 装到 Kindle（经 SSH，需 KINDLE_HOST）。
# 先备份已有插件和设置到 /mnt/us/koreader-backup-<日期>/
set -euo pipefail
cd "$(dirname "$0")/../plugin"
K="$(dirname "$0")/kssh.sh"; K="$(cd "$(dirname "$K")" && pwd)/kssh.sh"
TS=$(date +%Y%m%d%H%M)
"$K" "mkdir -p /mnt/us/koreader-backup-$TS && cp -a /mnt/us/koreader/settings.reader.lua /mnt/us/koreader-backup-$TS/ 2>/dev/null; [ -d /mnt/us/koreader/plugins/simpleui.koplugin ] && cp -a /mnt/us/koreader/plugins/simpleui.koplugin /mnt/us/koreader-backup-$TS/; rm -rf /mnt/us/koreader/settings/simpleui/news; true"
COPYFILE_DISABLE=1 tar -cf - simpleui.koplugin | "$K" "cd /mnt/us/koreader/plugins && rm -rf simpleui.koplugin && tar -xf -"
# 重启 KOReader（inspector 只监听回环，在 Kindle 上 curl）
"$K" "curl -s http://127.0.0.1:8080/koreader/event/Restart/ >/dev/null || true"
echo "已安装，KOReader 重启中。备份在 /mnt/us/koreader-backup-$TS"
