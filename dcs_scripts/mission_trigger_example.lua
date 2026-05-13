-- Voice-Comms-DCS mission trigger example
-- Place this in a Mission Editor DO SCRIPT action or adapt it into your mission framework.
-- These flags should match config/commands.json.

local function reset_flag(flag)
    trigger.action.setUserFlag(tostring(flag), 0)
end

local function poll_voice_flags()
    if trigger.misc.getUserFlag("5101") == 1 then
        trigger.action.outText("Voice: Request Tanker", 10)
        -- Add tanker-specific mission logic here.
        reset_flag(5101)
    end

    if trigger.misc.getUserFlag("5102") == 1 then
        trigger.action.outText("Voice: Request Bogey Dope", 10)
        -- Add AWACS / picture logic here.
        reset_flag(5102)
    end

    if trigger.misc.getUserFlag("5199") == 1 then
        trigger.action.outText("Voice: Abort Mission", 10)
        -- Add abort / RTB branch logic here.
        reset_flag(5199)
    end

    return timer.getTime() + 1.0
end

timer.scheduleFunction(poll_voice_flags, nil, timer.getTime() + 1.0)
