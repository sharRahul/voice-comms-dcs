-- Voice-Comms-DCS Export.lua
--
-- Copy this file to:
--   %USERPROFILE%\Saved Games\DCS\Scripts\Export.lua
-- or let the smart installer patch your existing Export.lua.
--
-- Safety note:
-- - This file does not use os.execute.
-- - It only loads VoiceBridge.lua and dcs_telemetry.lua from the same DCS Scripts folder.

local function vcdcs_log(component, message)
    local line = "[Voice-Comms-DCS:" .. tostring(component) .. "] " .. tostring(message)
    if env and env.info then
        env.info(line)
    else
        print(line)
    end
end

local function vcdcs_install_module(fileName, component)
    local path = lfs.writedir() .. [[Scripts\]] .. fileName
    local ok, moduleOrError = pcall(dofile, path)

    if not ok then
        vcdcs_log(component, "Failed to load " .. tostring(path) .. ": " .. tostring(moduleOrError))
        return
    end

    if type(moduleOrError) ~= "table" or type(moduleOrError.installExportCallbacks) ~= "function" then
        vcdcs_log(component, "Loaded " .. tostring(path) .. " but installExportCallbacks() was not found")
        return
    end

    local installOk, installError = pcall(moduleOrError.installExportCallbacks)
    if not installOk then
        vcdcs_log(component, "installExportCallbacks() failed: " .. tostring(installError))
        return
    end

    vcdcs_log(component, "Installed export callbacks from " .. tostring(path))
end

vcdcs_install_module("VoiceBridge.lua", "VoiceBridge")
vcdcs_install_module("dcs_telemetry.lua", "DcsTelemetry")
