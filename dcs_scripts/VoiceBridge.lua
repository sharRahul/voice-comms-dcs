-- Voice-Comms-DCS Lua bridge
-- Receives UDP packets from the Windows companion app and maps them to safe mission actions.
--
-- Packet format:
--   VCDCS|<command_id>|flag|<flag_number>|<flag_value>
--   VCDCS|<command_id>|command|<command_name>
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

local function is_safe_identifier(value)
    return type(value) == "string" and value:match("^[%w_%-%.]+$") ~= nil
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
        return false, "net.dostring_in failed: " .. tostring(result)
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
        return false, "handler failed: " .. tostring(err)
    end

    return false, "No Lua handler registered for command: " .. tostring(command_name)
end

function VoiceBridge.handlePacket(packet)
    if type(packet) ~= "string" or packet == "" then
        return false, "empty packet"
    end

    local fields = split_packet(packet)
    if fields[1] ~= "VCDCS" then
        return false, "invalid protocol prefix"
    end

    local command_id = fields[2] or "unknown"
    local action_type = fields[3]

    if not is_safe_identifier(command_id) then
        return false, "rejected unsafe command id"
    end

    if action_type == "flag" then
        local flag = fields[4]
        local value = fields[5] or "1"
        if not tostring(flag or ""):match("^%d+$") then
            return false, "flag must be numeric"
        end
        local ok, method_or_error = set_user_flag(flag, value)
        if ok then
            log("Command " .. command_id .. " set flag " .. flag .. "=" .. value .. " via " .. method_or_error)
            return true, method_or_error
        end
        return false, method_or_error
    end

    if action_type == "command" then
        local command_name = fields[4]
        local ok, method_or_error = dispatch_named_command(command_id, command_name)
        if ok then
            log("Command " .. command_id .. " dispatched custom command " .. tostring(command_name))
            return true, method_or_error
        end
        return false, method_or_error
    end

    return false, "unsupported action type: " .. tostring(action_type)
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
        local packet, receive_error = VoiceBridge.udp:receive()
        if not packet then
            if receive_error ~= "timeout" then
                VoiceBridge.lastError = tostring(receive_error)
            end
            return
        end

        local ok, result = VoiceBridge.handlePacket(packet)
        if not ok then
            log("Rejected packet: " .. tostring(result) .. " packet=" .. tostring(packet))
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
