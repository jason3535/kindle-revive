--[[--
hlsync — 把 KOReader 的划线/笔记推到自建同步服务器(见本仓库 cloud/worker.js)。

为什么不用自带的「导出划线」插件:它只能手动触发,Readwise 地址写死,而且丢掉章节/时间等字段。
这里在 关书 / 休眠 / 划线有改动 时把整本书的 annotations 原样做成快照,PUT 到
    <kosync 服务器>/hl/<md5(文件名)>
服务器地址和账号直接复用「进度同步」插件(kosync)的设置,不用再配一遍。
离线时快照先落盘到 cache/hlsync/,下次联网(onNetworkConnected)或打开书时补发。
整本覆盖写,重复推送无副作用。
--]]

local DataStorage = require("datastorage")
local Device = require("device")
local InfoMessage = require("ui/widget/infomessage")
local LuaSettings = require("luasettings")
local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local http = require("socket.http")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local ltn12 = require("ltn12")
local md5 = require("ffi/sha2").md5
local rapidjson = require("rapidjson")
local socket = require("socket")
local socketutil = require("socketutil")
local util = require("util")
local _ = require("gettext")

local QUEUE_DIR = DataStorage:getDataDir() .. "/cache/hlsync"
local KOSYNC_SETTINGS = DataStorage:getSettingsDir() .. "/kosync.lua"

local HLSync = WidgetContainer:extend{
    name = "hlsync",
    is_doc_only = true,
}

function HLSync:init()
    self.dirty = false
    self.ui.menu:registerToMainMenu(self)
end

-- 复用 kosync 的 custom_server / username / userkey
function HLSync:getCreds()
    local ok, s = pcall(function()
        return LuaSettings:open(KOSYNC_SETTINGS):readSetting("settings")
    end)
    if ok and type(s) == "table" and s.custom_server and s.username and s.userkey then
        return (s.custom_server:gsub("/+$", "")), s.username, s.userkey
    end
end

function HLSync:snapshot()
    if not self.ui or not self.ui.document or not self.ui.annotation then return end
    local file = self.ui.document.file
    if not file then return end
    local _, name = util.splitFilePathName(file)
    local props = self.ui.doc_props or {}
    local anns = {}
    for _, a in ipairs(self.ui.annotation.annotations or {}) do
        -- 纯书签没有选区(pos0)也没有高亮样式(drawer),text 只是"在 X 章节中"这类自动文字,不算划线
        if a.text and a.text ~= "" and (a.pos0 or a.drawer) then
            table.insert(anns, {
                text = a.text,
                note = a.note,
                chapter = a.chapter,
                datetime = a.datetime,
                pageno = a.pageno,
                pageref = a.pageref,
                page = type(a.page) == "string" and a.page or nil, -- 流式文档里是 xpointer
                drawer = a.drawer,
                color = a.color,
            })
        end
    end
    return {
        document = md5(name),      -- 与 kosync「按文件名匹配」的 digest 一致
        filename = name,
        title = props.display_title or props.title or name,
        authors = props.authors,
        device = Device.model,
        annotations = anns,
        snapshot_at = os.time(),
    }
end

function HLSync:enqueue(snap)
    util.makePath(QUEUE_DIR)
    local f = io.open(QUEUE_DIR .. "/" .. snap.document .. ".json", "w")
    if not f then return false end
    f:write(rapidjson.encode(snap))
    f:close()
    return true
end

function HLSync:upload(body, document)
    local server, user, key = self:getCreds()
    if not server then return false, "kosync not configured" end
    local sink = {}
    socketutil:set_timeout(5, 15)   -- 休眠路径上不能卡太久
    local code = socket.skip(1, http.request{
        url = server .. "/hl/" .. document,
        method = "PUT",
        source = ltn12.source.string(body),
        sink = ltn12.sink.table(sink),
        headers = {
            ["Content-Type"] = "application/json",
            ["Content-Length"] = #body,
            ["x-auth-user"] = user,
            ["x-auth-key"] = key,
        },
    })
    socketutil:reset_timeout()
    return code == 200, code
end

-- 把队列里所有快照推出去;成功的删掉,失败的留着下次再试
function HLSync:drain(interactive)
    if lfs.attributes(QUEUE_DIR, "mode") ~= "directory" then
        if interactive then UIManager:show(InfoMessage:new{ text = _("没有待同步的划线"), timeout = 2 }) end
        return
    end
    if not NetworkMgr:isConnected() then
        if interactive then UIManager:show(InfoMessage:new{ text = _("未联网,划线留在队列里"), timeout = 2 }) end
        return
    end
    local sent, failed = 0, 0
    for entry in lfs.dir(QUEUE_DIR) do
        local document = entry:match("^(%x+)%.json$")
        if document then
            local path = QUEUE_DIR .. "/" .. entry
            local f = io.open(path, "r")
            local body = f and f:read("*a")
            if f then f:close() end
            local ok, code = false, "empty"
            if body and #body > 0 then
                local pok, uok, ucode = pcall(self.upload, self, body, document)
                ok = pok and uok
                code = pok and ucode or uok   -- pcall 失败时 uok 是错误信息
            end
            if ok then
                os.remove(path)
                sent = sent + 1
            else
                failed = failed + 1
                logger.warn("hlsync: upload failed for", document, code)
            end
        end
    end
    logger.info("hlsync: drained", sent, "failed", failed)
    if interactive then
        UIManager:show(InfoMessage:new{
            text = failed == 0 and (sent > 0 and _("划线已同步") or _("没有待同步的划线")) or _("部分划线同步失败,稍后自动重试"),
            timeout = 2,
        })
    end
end

function HLSync:flush(force)
    if not (self.dirty or force) then return end
    local ok, snap = pcall(self.snapshot, self)
    if not ok or not snap then return end
    if self:enqueue(snap) then self.dirty = false end
    pcall(self.drain, self)
end

-- 事件:划线有改动就标脏;关书/休眠时落盘并尝试上传;联网/开书时补发队列
function HLSync:onAnnotationsModified()
    self.dirty = true
end

function HLSync:onCloseDocument()
    self:flush()
end

function HLSync:onSuspend()
    self:flush()
end

function HLSync:onNetworkConnected()
    UIManager:scheduleIn(1, function() pcall(self.drain, self) end)
end

function HLSync:onReaderReady()
    UIManager:scheduleIn(5, function() pcall(self.drain, self) end)
end

function HLSync:addToMainMenu(menu_items)
    menu_items.hlsync = {
        text = _("划线云同步"),
        sorting_hint = "tools",
        sub_item_table = {
            {
                text = _("立即同步本书划线"),
                enabled_func = function() return self:getCreds() ~= nil end,
                callback = function()
                    self.dirty = true
                    NetworkMgr:runWhenOnline(function() self:flush() end)
                end,
            },
            {
                text_func = function()
                    local server = self:getCreds()
                    return server and (_("服务器:") .. " " .. server) or _("未配置(先在「进度同步」里登录)")
                end,
                enabled = false,
            },
        },
    }
end

return HLSync
