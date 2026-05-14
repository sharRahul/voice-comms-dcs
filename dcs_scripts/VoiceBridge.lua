-- Voice-Comms-DCS Lua bridge
-- Receives UDP packets from the Windows companion app and maps them to safe mission actions.
--
-- Packet formats:
--   Legacy v1:
--     VCDCS|<command_id>|flag|<flag_number>|<flag_value>
--     VCDCS|<command_id>|command|<command_name>
--   Current v2, backward-compatible with v1:
--     VCDCS|v2|<sequence>|<command_id>|flag|<flag_number>|<flag_value>
--     VCDCS|v2|<sequence>|<command_id>|command|<command_name>
--
-- Recommended port: 10308

VoiceBridge = VoiceBridge or {}

VoiceBridge.host = VoiceBridge.host or "127.0.0.1"
VoiceBridge.port = VoiceBridge.port or 10308
VoiceBridge.socket = VoiceBridge.socket or nil
VoiceBridge.udp = VoiceBridge.udp or nil
VoiceBridge.enabled = true
VoiceBridge.lastError = nil
VoiceBridge.handlers = VoiceBridge.handlers or {}
VoiceBridge._exportInstalled = VoiceBridge._exportInstalled or false
VoiceBridge.replayWindowSize = VoiceBridge.replayWindowSize or 128
VoiceBridge.seenSequences = VoiceBridge.seenSequences or {}
VoiceBridge.seenSequenceOrder = VoiceBridge.seenSequenceOrder or {}

local function log(message)
    local line = "[VoiceBridge] " .. tostring(message)
    if env and env.info then
        env.info(line)
    else
        print(line)
    end
end

local function split_packet(packet)
    local fields = {}
    for part in string.gmatch(packet, "([^|]+)") do
        fields[#fields + 1] = part
    end
    return fields
end

local function packet_summary(packet)
    if type(packet) ~= "string" then
        return "non-string"
    end
    local prefix = packet:match("^([^|]+)") or "unknown"
    return "prefix=" .. tostring(prefix) .. " length=" .. tostring(#packet)
end

local function reason_code(reason)
    local text = tostring(reason or "rejected"):lower()
    text = text:gsub("[^%w_%-]+", "_")
    text = text:gsub("_+", "_")
    text = text:gsub("^_", ""):gsub("_$", "")
    if text == "" then
        return "rejected"
    end
    return string.sub(text, 1, 48)
end

local function is_safe_identifier(value)
    return type(value) == "string" and value:match("^[%w_%-%.]+$") ~= nil
end

local function is_sequence_seen(sequence)
    return VoiceBridge.seenSequences[tostring(sequence)] == true
end

local function remember_sequence(sequence)
    local key = tostring(sequence)
    if VoiceBridge.seenSequences[key] then
        return
    end
    VoiceBridge.seenSequences[key] = true
    VoiceBridge.seenSequenceOrder[#VoiceBridge.seenSequenceOrder + 1] = key
    while #VoiceBridge.seenSequenceOrder > VoiceBridge.replayWindowSize do
        local oldest = table.remove(VoiceBridge.seenSequenceOrder, 1)
        VoiceBridge.seenSequences[oldest] = nil
    end
end

local function send_ack(sequence, ok, reason, host, port)
    if not sequence or not VoiceBridge.udp or not host or not port then
        return
    end
    local status = ok and "ok" or ("rejected|" .. reason_code(reason))
    local ack = "VCDCS_ACK|" .. tostring(sequence) .. "|" .. status
    pcall(function()
        VoiceBridge.udp:sendto(ack, host, port)
    end)
end

local function set_user_flag(flag, value)
    local flag_text = tostring(flag)
    local numeric_value = tonumber(value) or 0

    if trigger and trigger.action and trigger.action.setUserFlag then
        trigger.action.setUserFlag(flag_text, numeric_value)
        return true, "trigger.action.setUserFlag"
    end

    -- In some Export.lua deployments, direct mission trigger APIs are unavailable.
    -- net.dostring_in is attempted only for a tightly formatted setUserFlag call.
    if net and net.dostring_in then
        local code = string.format(
            "trigger.action.setUserFlag(%q, %d)",
            flag_text,
            numeric_value
        )
        local ok, result = pcall(net.dostring_in, "mission", code)
        if ok then
            return true, "net.dostring_in mission bridge"
        end
        return false, "net.dostring_in failed"
    end

    return false, "No mission flag API available in this Lua environment"
end

local function dispatch_named_command(command_id, command_name)
    if not is_safe_identifier(command_name) then
        return false, "Rejected unsafe command name"
    end

    local handler = VoiceBridge.handlers[command_name]
    if type(handler) == "function" then
        local ok, err = pcall(handler, command_id)
        if ok then
            return true, "custom handler"
        end
        return false, "handler failed"
    end

    return false, "No Lua handler registered for command"
end

local function parse_packet(packet)
    if type(packet) ~= "string" or packet == "" then
        return nil, "empty packet"
    end

    local fields = split_packet(packet)
    if fields[1] ~= "VCDCS" then
        return nil, "invalid protocol prefix"
    end

    if fields[2] == "v2" then
        local sequence = tonumber(fields[3])
        if not sequence or sequence < 0 then
            return nil, "invalid sequence"
        end
        local parsed = {
            version = 2,
            sequence = tostring(fields[3]),
            command_id = fields[4] or "unknown",
            action_type = fields[5],
            arg1 = fields[6],
            arg2 = fields[7],
        }
        return parsed, nil
    end

    return {
        version = 1,
        sequence = nil,
        command_id = fields[2] or "unknown",
        action_type = fields[3],
        arg1 = fields[4],
        arg2 = fields[5],
    }, nil
end

function VoiceBridge.handlePacket(packet, sender_host, sender_port)
    local parsed, parse_error = parse_packet(packet)
    if not parsed then
        return false, parse_error
    end

    local command_id = parsed.command_id
    if not is_safe_identifier(command_id) then
        send_ack(parsed.sequence, false, "unsafe_command_id", sender_host, sender_port)
        return false, "rejected unsafe command id"
    end

    if parsed.version == 2 and is_sequence_seen(parsed.sequence) then
        send_ack(parsed.sequence, false, "duplicate_sequence", sender_host, sender_port)
        return false, "duplicate sequence"
    end

    if parsed.action_type == "flag" then
        local flag = parsed.arg1
        local value = parsed.arg2 or "1"
        if not tostring(flag or ""):match("^%d+$") then
            send_ack(parsed.sequence, false, "flag_not_numeric", sender_host, sender_port)
            return false, "flag must be numeric"
        end
        local ok, method_or_error = set_user_flag(flag, value)
        if ok then
            if parsed.version == 2 then
                remember_sequence(parsed.sequence)
            end
            send_ack(parsed.sequence, true, nil, sender_host, sender_port)
            log("Command " .. command_id .. " set flag " .. flag .. "=" .. value .. " via " .. method_or_error)
            return true, method_or_error
        end
        send_ack(parsed.sequence, false, method_or_error, sender_host, sender_port)
        return false, method_or_error
    end

    if parsed.action_type == "command" then
        local command_name = parsed.arg1
        local ok, method_or_error = dispatch_named_command(command_id, command_name)
        if ok then
            if parsed.version == 2 then
                remember_sequence(parsed.sequence)
            end
            send_ack(parsed.sequence, true, nil, sender_host, sender_port)
            log("Command " .. command_id .. " dispatched custom command " .. tostring(command_name))
            return true, method_or_error
        end
        send_ack(parsed.sequence, false, method_or_error, sender_host, sender_port)
        return false, method_or_error
    end

    send_ack(parsed.sequence, false, "unsupported_action", sender_host, sender_port)
    return false, "unsupported action type"
end

function VoiceBridge.start()
    if not VoiceBridge.enabled then
        return false, "bridge disabled"
    end

    if VoiceBridge.udp then
        return true, "already running"
    end

    local ok, socket_or_error = pcall(require, "socket")
    if not ok then
        VoiceBridge.lastError = "LuaSocket unavailable: " .. tostring(socket_or_error)
        log(VoiceBridge.lastError)
        return false, VoiceBridge.lastError
    end

    VoiceBridge.socket = socket_or_error
    local udp, udp_error = VoiceBridge.socket.udp()
    if not udp then
        VoiceBridge.lastError = "Unable to create UDP socket: " .. tostring(udp_error)
        log(VoiceBridge.lastError)
        return false, VoiceBridge.lastError
    end

    udp:settimeout(0)
    local bind_ok, bind_error = udp:setsockname(VoiceBridge.host, VoiceBridge.port)
    if not bind_ok then
        VoiceBridge.lastError = "Unable to bind UDP " .. VoiceBridge.host .. ":" .. VoiceBridge.port .. ": " .. tostring(bind_error)
        log(VoiceBridge.lastError)
        return false, VoiceBridge.lastError
    end

    VoiceBridge.udp = udp
    log("Listening on UDP " .. VoiceBridge.host .. ":" .. VoiceBridge.port)
    return true, "started"
end

function VoiceBridge.stop()
    if VoiceBridge.udp then
        VoiceBridge.udp:close()
        VoiceBridge.udp = nil
        log("Stopped")
    end
end

function VoiceBridge.poll()
    if not VoiceBridge.udp then
        return
    end

    while true do
        local packet, sender_host, sender_port = VoiceBridge.udp:receivefrom()
        if not packet then
            if sender_host ~= "timeout" then
                VoiceBridge.lastError = tostring(sender_host)
            end
            return
        end

        local ok, result = VoiceBridge.handlePacket(packet, sender_host, sender_port)
        if not ok then
            log("Rejected packet: " .. tostring(result) .. " " .. packet_summary(packet))
        end
    end
end

-- Mission Scripting / DO SCRIPT usage: call VoiceBridge.start(), then schedule polling.
function VoiceBridge.scheduleMissionPolling(interval_seconds)
    interval_seconds = interval_seconds or 0.10
    VoiceBridge.start()

    local function poll_and_reschedule()
        VoiceBridge.poll()
        return timer.getTime() + interval_seconds
    end

    if timer and timer.scheduleFunction then
        timer.scheduleFunction(poll_and_reschedule, nil, timer.getTime() + interval_seconds)
        log("Mission polling scheduled every " .. tostring(interval_seconds) .. " seconds")
    else
        log("timer.scheduleFunction unavailable; polling was not scheduled")
    end
end

-- Export.lua usage: call VoiceBridge.installExportCallbacks() after loading this file.
function VoiceBridge.installExportCallbacks()
    if VoiceBridge._exportInstalled then
        return
    end
    VoiceBridge._exportInstalled = true

    local previous_start = LuaExportStart
    local previous_stop = LuaExportStop
    local previous_after_next_frame = LuaExportAfterNextFrame

    LuaExportStart = function()
        if previous_start then
            previous_start()
        end
        VoiceBridge.start()
    end

    LuaExportAfterNextFrame = function()
        if previous_after_next_frame then
            previous_after_next_frame()
        end
        VoiceBridge.poll()
    end

    LuaExportStop = function()
        VoiceBridge.stop()
        if previous_stop then
            previous_stop()
        end
    end

    log("Export callbacks installed")
end

return VoiceBridge
