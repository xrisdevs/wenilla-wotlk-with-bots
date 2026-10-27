-- This client has no secure execution/taint model. Preserve post-hook return values;
-- do not replace an engine-provided implementation when one becomes available.
if not hooksecurefunc then
    function hooksecurefunc(owner, key, hook)
        if type(owner) == "string" then owner, key, hook = _G, owner, key end
        assert(type(owner) == "table" and type(owner[key]) == "function" and type(hook) == "function", "Invalid post-hook")
        local original = owner[key]
        local function pack(...) return {n=select("#", ...), ...} end
        owner[key] = function(...)
            local result = pack(original(...))
            hook(...)
            return unpack(result, 1, result.n)
        end
    end
end
if not IsLoggedIn then
    local loggedIn = false
    local f = CreateFrame("Frame")
    f:RegisterEvent("PLAYER_LOGIN")
    f:RegisterEvent("PLAYER_LOGOUT")
    f:SetScript("OnEvent", function(_, event) loggedIn = event == "PLAYER_LOGIN" end)
    function IsLoggedIn() return loggedIn end
end
-- The client cannot create override bindings yet, so there is never one to clear.
if not ClearOverrideBindings then
    function ClearOverrideBindings() end
end
if not issecurevariable then
    function issecurevariable() return false end
end
-- Implement post-script hooks using the client's real GetScript/SetScript methods.
for _, kind in ipairs({"Frame", "Cooldown", "StatusBar", "Button", "GameTooltip"}) do
    local sample = CreateFrame(kind)
    sample:Hide()
    local methods = getmetatable(sample).__index
    if type(methods) == "table" and not methods.HookScript then
        function methods:HookScript(event, hook)
            local previous = self:GetScript(event)
            self:SetScript(event, function(frame, ...)
                if previous then previous(frame, ...) end
                hook(frame, ...)
            end)
        end
    end
end
-- Textures never tile in this client; keep the 3.3.5 tiling flags so callers such as Gladius run.
do
    local sample = CreateFrame("Frame"):CreateTexture()
    local methods = getmetatable(sample).__index
    if type(methods) == "table" and not methods.SetHorizTile then
        function methods:SetHorizTile(tile) self.arenaHorizTile = tile and true or false end
        function methods:GetHorizTile() return self.arenaHorizTile or false end
    end
    if type(methods) == "table" and not methods.SetVertTile then
        function methods:SetVertTile(tile) self.arenaVertTile = tile and true or false end
        function methods:GetVertTile() return self.arenaVertTile or false end
    end
end
-- Keep the primary addon error available even if the stock error dialog itself fails.
ArenaAddonErrors = {}
local previousErrorHandler = geterrorhandler()
local handlingError = false
seterrorhandler(function(message)
    if handlingError then return end
    local text = tostring(message)
    if #ArenaAddonErrors < 30 then
        for _, name in ipairs({"ArenaCompat", "ArenaPvP", "InterruptBar", "LoseControl", "OmniCC", "Quartz", "Gladius", "SoundAlerter"}) do
            if string.find(text, "AddOns\\"..name.."\\", 1, true) then
                ArenaAddonErrors[#ArenaAddonErrors+1] = text
                break
            end
        end
    end
    if previousErrorHandler then
        handlingError = true
        pcall(previousErrorHandler, message)
        handlingError = false
    end
end)
