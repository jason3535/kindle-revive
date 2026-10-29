-- KOReader「进度同步」插件的设置文件,放到 Kindle 的 koreader/settings/kosync.lua
-- (scripts/setup_cloud_sync.sh 会自动生成并写入,这里只是说明格式)。
-- userkey = md5(密码) 的小写十六进制,和 Worker secret SYNC_KEY 相同。
return {
    ["settings"] = {
        ["auto_sync"] = true,          -- 开书拉 / 关书·休眠推,全自动
        ["checksum_method"] = 1,       -- 1 = 按文件名匹配(电脑端 cloud_sync.py 用 md5(文件名) 对应)
        ["custom_server"] = "https://ksync.example.com",
        ["kosync_hostname"] = "Kindle PW3",
        ["send_metadata"] = true,
        ["sync_backward"] = 3,         -- 服务器记录比本机旧:3 = 不动
        ["sync_forward"] = 2,          -- 服务器记录比本机新:2 = 静默跳过去
        ["username"] = "yourname",
        ["userkey"] = "<md5 of password>",
    },
}
