#!/usr/bin/env bash
# 便捷 SSH：./kssh.sh [命令]；KINDLE_HOST 必填。休眠刚唤醒时可能 refused，等几秒重试。
D=~/.config/mcp-show-on-kindle
exec ssh -i "$D/id_ed25519" -o IdentitiesOnly=yes -p 2222 -o ConnectTimeout=10 \
  -o UserKnownHostsFile="$D/known_hosts" -o HostKeyAlias=kindle "root@${KINDLE_HOST:?export KINDLE_HOST}" "$@"
