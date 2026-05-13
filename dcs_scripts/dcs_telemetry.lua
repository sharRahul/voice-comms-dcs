-- Voice-Comms-DCS Phase 2 telemetry exporter
-- Sends compact JSON-over-UDP telemetry to the local Python listener.
--
-- Safety constraints:
--   - No os.execute
--   - No arbitrary code execution
--   - Export.lua-only telemetry collection
--   - Localhost UDP by default

DcsTelemetry = DcsTelemetry or {}

DcsTelemetry.host = DcsTelemetry.host or "127.0.0.1"
DcsTelemetry.port = DcsTelemetry.port or 10309
DcsTelemetry.interval = DcsTelemetry.interval or 0.10 -- 10 Hz default to reduce DCS frame impact
DcsTelemetry.socket = DcsTelemetry.socket or nil
DcsTelemetry.udp = DcsTelemetry.udp or nil
DcsTelemetry.enabled = true
DcsTelemetry._lastSent = 0
DcsTelemetry._exportInstalled = DcsTelemetry._exportInstalled or false

local function log(message)
    local line = "[DcsTelemetry] " .. tostring(message)
    if env and env.info then
        env.info(line)
    else
        print(line)
    end
end

local function safe_call(fn, fallback)
    local ok, result = pcall(fn)
    if ok then
        return result
    end
    return fallback
end

local function number_or_nil(value)
    local number = tonumber(value)
    if number ~= nil and number == number then
        return number
    end
    return nil
end

local function feet(meters)
    local n = number_or_nil(meters)
    if not n then return nil end
    return n * 3.28084
end

local function knots(mps)
    local n = number_or_nil(mps)
    if not n then return nil end
    return n * 1.94384
end

local function degrees(rad)
    local n = number_or_nil(rad)
    if not n then return nil end
    local deg = n * 57.295779513
    while deg < 0 do deg = deg + 360 end
    while deg >= 360 do deg = deg - 360 end
    return deg
end

local function escape_json_string(value)
    value = tostring(value)
    value = value:gsub('\\', '\\\\')
    value = value:gsub('"', '\\"')
    value = value:gsub('\n', '\\n')
    value = value:gsub('\r', '\\r')
    value = value:gsub('\t', '\\t')
    return value
end

local function encode_json(value)
    local t = type(value)
    if value == nil then
        return "null"
    elseif t == "number" then
        if value ~= value or value == math.huge or value == -math.huge then
            return "null"
        end
        return string.format("%.6f", value)
    elseif t == "boolean" then
        return value and "true" or "false"
    elseif t == "string" then
        return '"' .. escape_json_string(value) .. '"'
    elseif t == "table" then
        local is_array = true
        local max_index = 0
        for k, _ in pairs(value) do
            if type(k) ~= "number" then
                is_array = false
                break
            end
            if k > max_index then max_index = k end
        end

        local parts = {}
        if is_array then
            for i = 1, max_index do
                parts[#parts + 1] = encode_json(value[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        end

        for k, v in pairs(value) do
            parts[#parts + 1] = '"' .. escape_json_string(k) .. '":' .. encode_json(v)
        end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return "null"
end

local function get_engine_rpm(engine_info, index)
    if type(engine_info) ~= "table" then return nil end
    if type(engine_info.RPM) == "table" then
        return number_or_nil(engine_info.RPM[index])
    end
    if index == 1 then
        return number_or_nil(engine_info.RPM)
    end
    return nil
end

local function get_fuel_total(payload)
    if type(payload) ~= "table" then return nil end
    return number_or_nil(payload.fuel) or number_or_nil(payload.Fuel) or number_or_nil(payload.fuel_internal)
end

local function get_locked_target()
    local target = safe_call(function()
        if LoGetLockedTargetInformation then
            return LoGetLockedTargetInformation()
        end
        if LoGetTargetInformation then
            return LoGetTargetInformation()
        end
        return nil
    end, nil)

    if type(target) ~= "table" then
        return nil
    end

    return {
        range_nm = number_or_nil(target.distance) and (tonumber(target.distance) / 1852.0) or number_or_nil(target.range_nm),
        bearing_deg = degrees(target.azimuth) or number_or_nil(target.bearing_deg),
        velocity_kt = knots(target.velocity) or number_or_nil(target.velocity_kt),
        aspect = target.aspect,
        type = target.type or target.Name or target.name,
    }
end

local function get_rwr_alerts()
    -- DCS does not expose a universal RWR API for every aircraft/module through Export.lua.
    -- This hook is intentionally conservative. Aircraft-specific adapters can populate it later.
    local alerts = safe_call(function()
        if LoGetRWRInfo then
            return LoGetRWRInfo()
        end
        return nil
    end, nil)

    if type(alerts) ~= "table" then
        return {}
    end

    local output = {}
    for i, alert in pairs(alerts) do
        if type(alert) == "table" then
            output[#output + 1] = {
                threat_type = alert.type or alert.name or alert.unitType or tostring(i),
                direction = alert.direction or alert.azimuth or alert.bearing,
                severity = alert.severity or alert.status or "spike",
            }
        end
    end
    return output
end

function DcsTelemetry.collect()
    local self_data = safe_call(function() return LoGetSelfData and LoGetSelfData() or nil end, {}) or {}
    local engine_info = safe_call(function() return LoGetEngineInfo and LoGetEngineInfo() or nil end, {}) or {}
    local payload = safe_call(function() return LoGetPayloadInfo and LoGetPayloadInfo() or nil end, {}) or {}
    local ias = safe_call(function() return LoGetIndicatedAirSpeed and LoGetIndicatedAirSpeed() or nil end, nil)
    local tas = safe_call(function() return LoGetTrueAirSpeed and LoGetTrueAirSpeed() or nil end, nil)
    local agl = safe_call(function() return LoGetAltitudeAboveGroundLevel and LoGetAltitudeAboveGroundLevel() or nil end, nil)
    local g = safe_call(function() return LoGetAccelerationUnits and LoGetAccelerationUnits() or nil end, nil)
    local gear = safe_call(function() return LoGetMechInfo and LoGetMechInfo() or nil end, {}) or {}

    local position = self_data.LatLongAlt or {}
    local heading = self_data.Heading

    return {
        protocol = "VCDCS_TELEMETRY",
        version = 1,
        timestamp = safe_call(function() return LoGetModelTime and LoGetModelTime() or 0 end, 0),
        aircraft = {
            name = self_data.Name,
            type = self_data.Type,
            coalition = self_data.Coalition,
        },
        internal = {
            fuel_total_kg = get_fuel_total(payload),
            fuel_internal_kg = get_fuel_total(payload),
            engine_rpm_left = get_engine_rpm(engine_info, 1),
            engine_rpm_right = get_engine_rpm(engine_info, 2),
            flaps = gear.flaps or gear.flapsPos,
            gear = gear.gear or gear.gearPos,
            g_load = number_or_nil(g),
        },
        spatial = {
            heading_deg = degrees(heading),
            altitude_asl_ft = feet(position.Alt),
            altitude_agl_ft = feet(agl),
            ias_kt = knots(ias),
            tas_kt = knots(tas),
            lat = position.Lat,
            lon = position.Long,
            x = self_data.Position and self_data.Position.x or nil,
            y = self_data.Position and self_data.Position.y or nil,
            z = self_data.Position and self_data.Position.z or nil,
        },
        tactical = {
            locked_target = get_locked_target(),
            rwr_alerts = get_rwr_alerts(),
        },
    }
end

function DcsTelemetry.start()
    if not DcsTelemetry.enabled then
        return false, "disabled"
    end
    if DcsTelemetry.udp then
        return true, "already running"
    end

    local ok, socket_or_error = pcall(require, "socket")
    if not ok then
        log("LuaSocket unavailable: " .. tostring(socket_or_error))
        return false, tostring(socket_or_error)
    end

    DcsTelemetry.socket = socket_or_error
    local udp, err = DcsTelemetry.socket.udp()
    if not udp then
        log("Unable to create UDP socket: " .. tostring(err))
        return false, tostring(err)
    end
    udp:settimeout(0)
    DcsTelemetry.udp = udp
    log("Telemetry UDP target " .. DcsTelemetry.host .. ":" .. tostring(DcsTelemetry.port))
    return true, "started"
end

function DcsTelemetry.stop()
    if DcsTelemetry.udp then
        DcsTelemetry.udp:close()
        DcsTelemetry.udp = nil
        log("Stopped")
    end
end

function DcsTelemetry.exportFrame()
    if not DcsTelemetry.udp then
        return
    end

    local now = safe_call(function() return LoGetModelTime and LoGetModelTime() or 0 end, 0)
    if now - DcsTelemetry._lastSent < DcsTelemetry.interval then
        return
    end
    DcsTelemetry._lastSent = now

    local packet = encode_json(DcsTelemetry.collect())
    DcsTelemetry.udp:sendto(packet, DcsTelemetry.host, DcsTelemetry.port)
end

function DcsTelemetry.installExportCallbacks()
    if DcsTelemetry._exportInstalled then
        return
    end
    DcsTelemetry._exportInstalled = true

    local previous_start = LuaExportStart
    local previous_stop = LuaExportStop
    local previous_after_next_frame = LuaExportAfterNextFrame

    LuaExportStart = function()
        if previous_start then previous_start() end
        DcsTelemetry.start()
    end

    LuaExportAfterNextFrame = function()
        if previous_after_next_frame then previous_after_next_frame() end
        DcsTelemetry.exportFrame()
    end

    LuaExportStop = function()
        DcsTelemetry.stop()
        if previous_stop then previous_stop() end
    end

    log("Export callbacks installed")
end

return DcsTelemetry
