#!/usr/bin/env bash
# 在电脑上运行：生成专用密钥并装到 Kindle KOReader SSH（首次需先开启 KOReader SSH 的「无密码登录」或用 USB 拷贝）。
# 用法: KINDLE_HOST=<Kindle IP> ./install_ssh_key.sh
set -euo pipefail
: "${KINDLE_HOST:?请 export KINDLE_HOST=<Kindle 局域网 IP>}"
D=~/.config/mcp-show-on-kindle; mkdir -p "$D"; chmod 700 "$D"
[ -f "$D/id_ed25519" ] || ssh-keygen -t ed25519 -N "" -f "$D/id_ed25519" -C kindle
cat "$D/id_ed25519.pub" | ssh -p 2222 -o HostKeyAlias=kindle -o UserKnownHostsFile="$D/known_hosts" root@"$KINDLE_HOST" \
  'mkdir -p /mnt/us/koreader/settings/SSH && cat >> /mnt/us/koreader/settings/SSH/authorized_keys'
echo "完成。之后可在 KOReader SSH 设置里关掉无密码登录。"
