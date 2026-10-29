#!/usr/bin/env bash
# 一键把 Kindle 接到云端同步服务器(cloud/worker.js 已部署之后跑):
#   1) 写 koreader/settings/kosync.lua(进度同步插件的服务器+账号,自动同步开)
#   2) 安装 plugin/hlsync.koplugin(划线快照上传)
#   3) 经 inspector 把「Wi-Fi 关闭时的操作」设为自动开启(auto_sync 的前提),然后重启 KOReader
# 需要:KINDLE_HOST、Kindle 醒着(inspector 只在醒着时开)、~/.config/kindle-sync/env 里有
#   KSYNC_URL / KSYNC_USER / KSYNC_KEY(KEY = md5(密码))。
set -euo pipefail
cd "$(dirname "$0")/.."
K="$(pwd)/scripts/kssh.sh"
# shellcheck disable=SC1090
source ~/.config/kindle-sync/env
: "${KSYNC_URL:?}" "${KSYNC_USER:?}" "${KSYNC_KEY:?}"

"$K" "cat > /mnt/us/koreader/settings/kosync.lua <<LUA
-- we can read Lua syntax here!
return {
    [\"settings\"] = {
        [\"auto_sync\"] = true,
        [\"checksum_method\"] = 1,
        [\"custom_server\"] = \"$KSYNC_URL\",
        [\"kosync_hostname\"] = \"Kindle\",
        [\"send_metadata\"] = true,
        [\"sync_backward\"] = 3,
        [\"sync_forward\"] = 2,
        [\"username\"] = \"$KSYNC_USER\",
        [\"userkey\"] = \"$KSYNC_KEY\",
    },
}
LUA
/mnt/us/koreader/luajit -e 'assert(loadfile(\"/mnt/us/koreader/settings/kosync.lua\"))' && echo 'kosync.lua 已写入'"

COPYFILE_DISABLE=1 tar -C plugin -cf - hlsync.koplugin | "$K" "cd /mnt/us/koreader/plugins && rm -rf hlsync.koplugin && tar -xf - && echo 'hlsync.koplugin 已安装'"

"$K" 'I=http://127.0.0.1:8080/koreader
wget -q -O- -T 5 "$I/g_settings/saveSetting/%22wifi_enable_action%22/%22turn_on%22/" >/dev/null || { echo "inspector 不通:Kindle 要醒着"; exit 1; }
wget -q -O- -T 5 "$I/g_settings/saveSetting/%22wifi_disable_action%22/%22leave_on%22/" >/dev/null
wget -q -O- -T 5 "$I/g_settings/flush/" >/dev/null
echo "Wi-Fi 动作已设为自动;重启 KOReader…"
wget -q -O- -T 5 "$I/broadcast/Restart/" >/dev/null'   # 注意是 broadcast,event/Restart 只发给最上层控件,常常没反应
echo "完成。打开一本书看 KOReader 顶部菜单 → 工具 → 进度同步 应显示已登录。"
