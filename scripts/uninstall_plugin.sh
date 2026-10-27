#!/usr/bin/env bash
# 卸载 AI Podcast SimpleUI：删除插件目录并重启 KOReader。
set -euo pipefail
K="$(cd "$(dirname "$0")" && pwd)/kssh.sh"
"$K" "rm -rf /mnt/us/koreader/plugins/simpleui.koplugin /mnt/us/koreader/settings/simpleui/news; curl -s http://127.0.0.1:8080/koreader/event/Restart/ >/dev/null || true"
echo "已卸载。"
