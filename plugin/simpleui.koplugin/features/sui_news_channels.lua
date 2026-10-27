-- Channels of AI Podcast (aipodcast.jasonlin.tech): every person is a
-- channel; groups are the person's primary field (source.category, from
-- pipeline/gen_kindle_api.py). The group prefix is kept so saved per-channel
-- state from the Qiaomu build stays valid.
local M = {}

M.GROUPS = { "deep-learning", "nlp", "product", "safety", "robotics", "rl", "bio" }
M.GROUP_PREFIX = "@qiaomu:"

local KNOWN = {}
for _, group in ipairs(M.GROUPS) do KNOWN[group] = true end

local function enabled(source) return source.enabled ~= false end

function M.group(source)
    return KNOWN[source.category] and source.category or "product"
end

function M.channels(sources)
    local result = {}
    for _, source in ipairs(sources) do
        if enabled(source) then result[#result + 1] = source end
    end
    return result
end

function M.community() return {} end

--- Channel sources of one group, in catalog order.
function M.groupSources(sources, group)
    local result = {}
    for _, source in ipairs(M.channels(sources)) do
        if M.group(source) == group then result[#result + 1] = source end
    end
    return result
end

function M.isGroup(channel) return type(channel) == "string" and channel:sub(1, #M.GROUP_PREFIX) == M.GROUP_PREFIX end

--- Returns a predicate selecting the entries of `channel` (nil = everything).
function M.filter(sources, channel)
    if not channel then return function() return true end end
    if M.isGroup(channel) then
        local ids = {}
        for _, source in ipairs(M.groupSources(sources, channel:sub(#M.GROUP_PREFIX + 1))) do ids[source.id] = true end
        return function(entry) return ids[entry.sourceId] == true end
    end
    return function(entry) return entry.sourceId == channel end
end

return M
