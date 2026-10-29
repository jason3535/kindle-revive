#!/bin/zsh
# Kindle ↔ Apple Books 自动同步循环。必须在「终端」App 里跑(Apple Books 的读取授权只给了终端)。
# 用法:双击,或 open -a Terminal autosync.command;关掉窗口即停止。参数 1 = 间隔秒数(默认 600)。
# 每轮:1) Apple Books 位置 → 云端(cloud_sync.py push --quiet,位置没变不推)
#       2) 拉 Kindle 划线(云端快照 + 插着线时的 U 盘),有新内容才重建高亮站 index.html
SYNC_DIR=${SYNC_DIR:-$HOME/Downloads/kindle-sync}
HL_DIR=${HL_DIR:-$HOME/kindle-highlights}
INTERVAL=${1:-600}
LOG=$HOME/.config/kindle-sync/autosync.log
mkdir -p "$(dirname "$LOG")"
say() { echo "$(date '+%m-%d %H:%M') $*" | tee -a "$LOG"; }
say "自动同步启动,每 $((INTERVAL/60)) 分钟一轮;关掉这个窗口即停止"
while :; do
  out=$(cd "$SYNC_DIR" && python3 cloud_sync.py push --quiet 2>&1) && [ -n "$out" ] && say "$out"
  if [ -d "$HL_DIR" ]; then
    before=$(shasum "$HL_DIR/koreader.json" 2>/dev/null | cut -c1-40)
    (cd "$HL_DIR" && python3 parse_koreader.py --pull >/dev/null 2>&1)
    after=$(shasum "$HL_DIR/koreader.json" 2>/dev/null | cut -c1-40)
    if [ "$before" != "$after" ]; then
      n=$(python3 -c "import json;print(json.load(open('$HL_DIR/koreader.json'))['stats']['entries'])" 2>/dev/null)
      if (cd "$HL_DIR" && python3 build.py >/dev/null 2>&1); then
        say "Kindle 划线有变化(现 ${n} 条),高亮站已重建"
      else
        say "Kindle 划线有变化但页面重建失败,下轮重试"
      fi
    fi
  fi
  sleep "$INTERVAL"
done
