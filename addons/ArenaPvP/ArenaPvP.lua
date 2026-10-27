-- Integration defaults, MIT. Third-party addons retain their upstream licenses.
local frame = CreateFrame("Frame")
ArenaPvPStatus = {}
local loaded = false
frame:SetScript("OnUpdate", function()
    if loaded or not IsLoggedIn() or not GetSpellInfo(6552) or not ArenaInterruptBarRefresh then return end
    loaded = true
    for _, name in ipairs({"InterruptBar", "LoseControl", "OmniCC", "Quartz"}) do
        ArenaPvPStatus[name] = IsAddOnLoaded(name) and "loaded" or "not loaded"
    end
    -- Demand-load once spell names and the unit APIs are available. AceAddon handles
    -- late initialization through ADDON_LOADED and IsLoggedIn.
    for _, name in ipairs({"Gladius", "SoundAlerter"}) do
        if UnitGUID and GetNumArenaOpponents then
            local ok, reason = LoadAddOn(name)
            ArenaPvPStatus[name] = ok and "loaded" or (reason or "load failed")
        else
            ArenaPvPStatus[name] = "requires updated client unit APIs"
        end
    end
    ArenaPvPDB = ArenaPvPDB or {}
    ArenaPvPDB.characters = ArenaPvPDB.characters or {}
    local character = (UnitName("player") or "").."-"..GetRealmName()
    local firstAccount = not ArenaPvPDB.configured
    local firstCharacter = not ArenaPvPDB.characters[character]
    local width, height = UIParent:GetWidth(), UIParent:GetHeight()
    ArenaPvPDB.opponentDefaults = ArenaPvPDB.opponentDefaults or {}
    if not ArenaPvPDB.opponentDefaults[character] and Gladius and Gladius.db then
        local p = Gladius.db.profile
        p.x, p.y = width * 0.76, height * 0.68
        p.frameScale, p.barWidth, p.barHeight = 1, 190, 30
        p.locked, p.drCooldown, p.castBar, p.trinketStatus = true, true, true, true
        p.minimapIcon.hide = true
        for _, key in ipairs({"enemyAnnounce", "specAnnounce", "trinketUpAnnounce", "trinketUsedAnnounce", "lowHealthAnnounce", "drinkAnnounce", "resAnnounce", "auraAnnounce", "cooldownAnnounce"}) do p[key] = false end
        Gladius:UpdateFrame()
        ArenaPvPDB.opponentDefaults[character] = true
    end
    if firstAccount and InterruptBarDB then
        InterruptBarDB.scale, InterruptBarDB.hidden, InterruptBarDB.lock = 1.1, true, true
        -- Reposition immediately, including the first login.
        InterruptBarDB.Position = {point="CENTER", relativePoint="CENTER", xOfs=-180, yOfs=-150}
        if ArenaInterruptBarRefresh then ArenaInterruptBarRefresh() end
    end
    if firstCharacter and LoseControlDB and LoseControlDB.frames then
        LoseControlDB.tracking.Root = true
        local p = LoseControlDB.frames.player
        p.size, p.anchor, p.point, p.relativePoint, p.x, p.y = 52, "None", "CENTER", "CENTER", 0, -80
        for i=1,5 do LoseControlDB.frames["arena"..i].enabled = false end
    end
    local ace = LibStub and LibStub("AceAddon-3.0", true)
    local quartz = ace and ace:GetAddon("Quartz3", true)
    if firstAccount and quartz and quartz.db then
        for _, name in ipairs({"Buff", "Flight", "Swing", "Timer", "Mirror", "Pet", "Tradeskill", "GCD", "Range"}) do
            quartz.db.profile.modules[name] = false
            local module = quartz:GetModule(name, true)
            if module then module:Disable() end
        end
        for name, y in pairs({Player=height*.25, Target=height*.31, Focus=height*.37}) do
            local module = quartz:GetModule(name, true)
            if module and module.db then
                local p = module.db.profile
                p.w, p.h, p.scale, p.x, p.y = 250, 22, 1, width/2-125, y
            end
        end
        quartz:ApplySettings()
    end
    if not ArenaPvPDB.soundDefaults and SoundAlerter and SoundAlerter.db1 then
        local p = SoundAlerter.db1.profile
        p.chatalerts = true -- This upstream setting means DISABLE chat alerts.
        p.field, p.all, p.arena, p.battleground = false, false, true, true
        p.enemyinrange, p.class, p.drinking = false, false, true
        ArenaPvPDB.soundDefaults = true
        SoundAlerter:PLAYER_ENTERING_WORLD()
    end
    if firstAccount and OmniCC then
        OmniCC:SetFontSize(20)
        OmniCC:SetMinDuration(2)
        OmniCC:SetEffect("none")
    end
    if LoseControlDB then
        for unit in pairs(LoseControlDB.frames) do
            local icon = _G["LoseControl"..unit]
            if icon then icon:PLAYER_ENTERING_WORLD(); icon:UNIT_AURA(unit) end
        end
    end
    ArenaPvPDB.configured = true
    ArenaPvPDB.characters[character] = true
end)

SLASH_ARENAPVP1 = "/pvpaddons"
SlashCmdList.ARENAPVP = function()
    for _, name in ipairs({"InterruptBar", "LoseControl", "OmniCC", "Quartz", "Gladius", "SoundAlerter"}) do
        DEFAULT_CHAT_FRAME:AddMessage(name..": "..(ArenaPvPStatus[name] or "waiting for game data"))
    end
end
