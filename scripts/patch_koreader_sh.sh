#!/bin/sh
# 在 Kindle 上运行（SSH 登录后）：给 koreader.sh 加 8080 防火墙规则。可重复执行。
set -e
F=/mnt/us/koreader/koreader.sh
RULE='iptables -I INPUT 1 -p tcp --dport 8080 ! -i lo -j DROP'
grep -qF -- "$RULE" "$F" && { echo "已存在，跳过"; exit 0; }
cp "$F" "$F.bak"
sed -i "/iptables -A INPUT -i wlan0 -p udp --dport 8134 -j ACCEPT/a\\    $RULE" "$F"
grep -nF -- "$RULE" "$F" && echo "OK，重启 KOReader 生效；还原：cp $F.bak $F"
