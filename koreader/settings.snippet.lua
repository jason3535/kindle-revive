-- 推荐直接在 KOReader 菜单里设置（工具 → 更多工具 → SSH 服务器 / HTTP inspector），效果等同下面这些键。
-- 如要手改 /mnt/us/koreader/settings.reader.lua：先退出 KOReader 再改，否则会被内存中的设置覆盖。
-- SSH：开机自启 + 端口 2222 + 只允许密钥登录（公钥放 /mnt/us/koreader/settings/SSH/authorized_keys）
["SSH_autostart"] = true,
["SSH_port"] = "2222",
["SSH_key_only_auth"] = true,
["SSH_allow_no_password"] = false,
-- HTTP inspector：开机自启，端口 8080（配合 koreader.sh 的 iptables 规则只允许回环访问）
["httpinspector"] = {
    ["autostart"] = true,
    ["port"] = 8080,
},
