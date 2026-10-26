-- BotArena Spectator (WoW 3.3.5a): tournament-style spectator overlay + match control panel.
-- Data comes from the server as "BOTARENA" addon messages:
--   S;state;elapsed;type;winner;mapId;match;bgStatus
--   B;idx;team;name;class;spec;hp;maxhp;pw;maxpw;ptype;alive;target;castId;castLeft;castTotal;x;y
--   A;idx;spellId:remainingMs:flag,...      (flag c = crowd control, d = debuff, b = buff)
--   E;seq;casterIdx;spellId;targetIdx;ageMs  (a cast happened)
-- Slash: /ba  (panel | cam <1-10|name|auto|off> | spectate | start ... | stop | auto on|off | ui | hide | show | reset)

local PREFIX = "BOTARENA"
BotArenaSpectatorDB = BotArenaSpectatorDB or {}
local db = BotArenaSpectatorDB

-- ------------------------------------------------------------------ static data
local CLASS_NAMES  = { [1]="Warrior",[2]="Paladin",[3]="Hunter",[4]="Rogue",[5]="Priest",[6]="Death Knight",[7]="Shaman",[8]="Mage",[9]="Warlock",[11]="Druid" }
local CLASS_TOKENS = { [1]="WARRIOR",[2]="PALADIN",[3]="HUNTER",[4]="ROGUE",[5]="PRIEST",[6]="DEATHKNIGHT",[7]="SHAMAN",[8]="MAGE",[9]="WARLOCK",[11]="DRUID" }
local SPEC_NAMES = { "Arms","Fury","Protection","Holy","Protection","Retribution","Beast Mastery","Marksmanship","Survival",
  "Assassination","Combat","Subtlety","Discipline","Holy","Shadow","Blood","Frost","Unholy","Elemental","Enhancement","Restoration",
  "Arcane","Fire","Frost","Affliction","Demonology","Destruction","Balance","Feral","Restoration" }
local POWER_COLORS = { [0]={0.2,0.45,1}, [1]={1,0.15,0.15}, [2]={1,0.6,0}, [3]={1,1,0.3}, [6]={0.3,0.8,1} }
local GOLD, GREEN = { 1, 0.82, 0.2 }, { 0.35, 1, 0.35 }

local ARENAS = { { "random", "Random" }, { "na", "Nagrand Arena" }, { "be", "Blade's Edge" }, { "rl", "Ruins of Lordaeron" }, { "rv", "Ring of Valor" } }
local TYPES = { { "2", "2v2" }, { "3", "3v3" }, { "5", "5v5" } }
local PRESETS = {
  { "random", "Random preset", 0 },
  { "rmp", "RMP (Rogue/Mage/Priest)", 3 }, { "tsg", "TSG (Warrior/DK/HPal)", 3 }, { "beastcleave", "Beastcleave", 3 },
  { "wls", "WLS (War/Lock/RSham)", 3 }, { "shadowplay", "Shadowplay", 3 }, { "lsd", "LSD", 3 }, { "kittycleave", "Kitty Cleave", 3 },
  { "pmr", "PMR (HPal/Mage/Rogue)", 3 }, { "thugcleave", "Thug Cleave", 3 }, { "mld", "MLD", 3 }, { "rls", "RLS", 3 }, { "wmp", "WMP", 3 },
  { "rp", "Rogue/Disc (2v2)", 2 }, { "ww", "War/RDruid (2v2)", 2 }, { "ml", "Mage/Lock (2v2)", 2 }, { "dkh", "DK/HPal (2v2)", 2 },
}

-- Major arena cooldowns, keyed by spell name (rank independent). Seconds.
local COOLDOWNS = {
  -- warrior
  ["Bladestorm"]=90, ["Shield Wall"]=300, ["Intervene"]=30, ["Charge"]=15, ["Intercept"]=30, ["Retaliation"]=300, ["Recklessness"]=300,
  ["Berserker Rage"]=30, ["Pummel"]=10, ["Shield Bash"]=12, ["Spell Reflection"]=10, ["Disarm"]=60, ["Concussion Blow"]=30, ["Shockwave"]=20,
  -- paladin
  ["Divine Shield"]=300, ["Hand of Protection"]=300, ["Hand of Freedom"]=25, ["Hammer of Justice"]=40, ["Avenging Wrath"]=180, ["Divine Plea"]=60,
  ["Lay on Hands"]=1200, ["Repentance"]=60, ["Aura Mastery"]=120, ["Divine Protection"]=180, ["Hand of Sacrifice"]=120, ["Holy Shock"]=6, ["Divine Favor"]=120,
  -- hunter
  ["Deterrence"]=90, ["Scatter Shot"]=30, ["Silencing Shot"]=20, ["Readiness"]=180, ["Wyvern Sting"]=60, ["Disengage"]=25, ["Rapid Fire"]=300,
  ["Bestial Wrath"]=120, ["Freezing Arrow"]=30, ["Freezing Trap"]=30, ["Intimidation"]=60, ["Feign Death"]=30, ["Master's Call"]=60,
  -- rogue
  ["Kidney Shot"]=20, ["Blind"]=180, ["Cloak of Shadows"]=90, ["Evasion"]=180, ["Vanish"]=180, ["Shadowstep"]=20, ["Preparation"]=480,
  ["Sprint"]=180, ["Kick"]=10, ["Dismantle"]=60, ["Shadow Dance"]=60, ["Cold Blood"]=180, ["Adrenaline Rush"]=180, ["Killing Spree"]=120, ["Gouge"]=10,
  -- priest
  ["Psychic Scream"]=27, ["Pain Suppression"]=180, ["Power Infusion"]=120, ["Dispersion"]=120, ["Silence"]=45, ["Psychic Horror"]=120,
  ["Penance"]=10, ["Fear Ward"]=180, ["Inner Focus"]=180, ["Shadowfiend"]=300, ["Desperate Prayer"]=120, ["Guardian Spirit"]=180, ["Mind Blast"]=8,
  -- death knight
  ["Strangulate"]=120, ["Mind Freeze"]=10, ["Anti-Magic Shell"]=45, ["Icebound Fortitude"]=120, ["Death Grip"]=35, ["Gnaw"]=60,
  ["Summon Gargoyle"]=180, ["Unholy Frenzy"]=180, ["Lichborne"]=120, ["Anti-Magic Zone"]=120, ["Empower Rune Weapon"]=300, ["Hungering Cold"]=60,
  -- shaman
  ["Wind Shear"]=6, ["Grounding Totem"]=15, ["Hex"]=45, ["Bloodlust"]=300, ["Heroism"]=300, ["Elemental Mastery"]=180, ["Nature's Swiftness"]=120,
  ["Shamanistic Rage"]=60, ["Thunderstorm"]=45, ["Feral Spirit"]=180, ["Tremor Totem"]=0, ["Riptide"]=6, ["Stoneclaw Totem"]=60,
  -- mage
  ["Counterspell"]=24, ["Ice Block"]=300, ["Blink"]=15, ["Deep Freeze"]=30, ["Cold Snap"]=480, ["Icy Veins"]=180, ["Frost Nova"]=25,
  ["Evocation"]=240, ["Mirror Image"]=180, ["Invisibility"]=180, ["Dragon's Breath"]=20, ["Blast Wave"]=30, ["Presence of Mind"]=120, ["Arcane Power"]=120,
  -- warlock
  ["Death Coil"]=120, ["Howl of Terror"]=40, ["Spell Lock"]=24, ["Shadowfury"]=20, ["Demonic Circle: Teleport"]=30, ["Soulshatter"]=180,
  ["Metamorphosis"]=180, ["Fel Domination"]=180, ["Devour Magic"]=8, ["Seduction"]=0,
  -- druid
  ["Bash"]=60, ["Maim"]=10, ["Nature's Grasp"]=60, ["Barkskin"]=60, ["Innervate"]=180, ["Feral Charge - Bear"]=15, ["Feral Charge - Cat"]=30,
  ["Berserk"]=180, ["Survival Instincts"]=180, ["Frenzied Regeneration"]=180, ["Swiftmend"]=15, ["Starfall"]=90, ["Typhoon"]=20, ["Dash"]=180, ["Skull Bash"]=60,
}

-- ------------------------------------------------------------------ state
local state = { bots = {}, auras = {}, status = {}, events = {}, lastSeq = 0 }
local history = {}   -- idx -> { {spellId, t}, ... }
local cooldowns = {} -- idx -> { [spellName] = { icon=, start=, dur= } }
local lastSnapshot = 0

local function cmd(text)
  if db.lobby then
    local target = text:match("^%.botarena cam (%S+)$")
    if target then SendChatMessage(".botarena view " .. target, "SAY") end
    return
  end
  SendChatMessage(text, "SAY")
end
local function classColor(cls) local c = RAID_CLASS_COLORS[CLASS_TOKENS[cls] or ""]; if c then return c.r, c.g, c.b end return 0.8, 0.8, 0.8 end
local function spellIcon(id) local _, _, icon = GetSpellInfo(id); return icon or "Interface\\Icons\\INV_Misc_QuestionMark" end
local function spellName(id) return (GetSpellInfo(id)) or ("spell " .. tostring(id)) end
local function fmt(n) n = tonumber(n) or 0; if n >= 1000 then return string.format("%.1fk", n / 1000) end return tostring(n) end
local function split(str, sep) local out = {}; for piece in string.gmatch(str .. sep, "(.-)" .. sep) do out[#out + 1] = piece end return out end
local function teamColor(team) return (team == "A") and GOLD or GREEN end

-- ------------------------------------------------------------------ root / top bar
local root = CreateFrame("Frame", "BotArenaSpectatorRoot", UIParent)
root:SetAllPoints(UIParent)
root:SetFrameStrata("MEDIUM")

local top = CreateFrame("Frame", nil, root)
top:SetWidth(560); top:SetHeight(64)
top:SetPoint("TOP", root, "TOP", 0, -6)
top:SetBackdrop({ bgFile = "Interface\\ChatFrame\\ChatFrameBackground", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
top:SetBackdropColor(0, 0, 0, 0.75); top:SetBackdropBorderColor(0.6, 0.6, 0.6, 0.9)

top.arena = top:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge"); top.arena:SetPoint("TOP", top, "TOP", 0, -6)
top.timer = top:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"); top.timer:SetPoint("TOP", top.arena, "BOTTOM", 0, -2); top.timer:SetText("00:00")
top.gold = top:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"); top.gold:SetPoint("LEFT", top, "LEFT", 16, 0); top.gold:SetTextColor(unpack(GOLD)); top.gold:SetText("GOLD")
top.green = top:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"); top.green:SetPoint("RIGHT", top, "RIGHT", -16, 0); top.green:SetTextColor(unpack(GREEN)); top.green:SetText("GREEN")
top.goldAlive = top:CreateFontString(nil, "OVERLAY", "GameFontHighlight"); top.goldAlive:SetPoint("TOP", top.gold, "BOTTOM", 0, -2)
top.greenAlive = top:CreateFontString(nil, "OVERLAY", "GameFontHighlight"); top.greenAlive:SetPoint("TOP", top.green, "BOTTOM", 0, -2)
top.phase = top:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); top.phase:SetPoint("BOTTOM", top, "BOTTOM", 0, 5)

-- The stock "Gold Team: N Players Remaining" world-state text sits exactly under our top bar: keep it hidden.
local function hideWorldState()
  if WorldStateAlwaysUpFrame then WorldStateAlwaysUpFrame:SetAlpha(root:IsShown() and 0 or 1) end
end
pcall(function() if WorldStateAlwaysUpFrame and WorldStateAlwaysUpFrame.HookScript then WorldStateAlwaysUpFrame:HookScript("OnShow", hideWorldState) end end)
hideWorldState()

local banner = root:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
banner:SetPoint("CENTER", root, "CENTER", 0, 120); banner:SetTextHeight(42); banner:Hide()

-- ------------------------------------------------------------------ team frames
local FRAME_W, FRAME_H, GAP = 320, 118, 10
local frames = { A = {}, H = {} }

local function makeBotFrame(team, i)
  local color = teamColor(team)
  local f = CreateFrame("Button", nil, root)
  f:SetWidth(FRAME_W); f:SetHeight(FRAME_H)
  if team == "A" then f:SetPoint("TOPLEFT", root, "TOPLEFT", 14, -90 - (i - 1) * (FRAME_H + GAP))
  else f:SetPoint("TOPRIGHT", root, "TOPRIGHT", -14, -90 - (i - 1) * (FRAME_H + GAP)) end
  f:SetBackdrop({ bgFile = "Interface\\ChatFrame\\ChatFrameBackground", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
  f:SetBackdropColor(0, 0, 0, 0.7); f:SetBackdropBorderColor(color[1], color[2], color[3], 0.9)
  local left = (team == "A")

  -- portrait (class icon)
  f.portrait = f:CreateTexture(nil, "ARTWORK"); f.portrait:SetWidth(54); f.portrait:SetHeight(54)
  f.portrait:SetTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Classes")
  if left then f.portrait:SetPoint("TOPLEFT", f, "TOPLEFT", 8, -8) else f.portrait:SetPoint("TOPRIGHT", f, "TOPRIGHT", -8, -8) end
  f.portraitBorder = f:CreateTexture(nil, "OVERLAY"); f.portraitBorder:SetPoint("TOPLEFT", f.portrait, -2, 2); f.portraitBorder:SetPoint("BOTTOMRIGHT", f.portrait, 2, -2)
  f.portraitBorder:SetTexture(color[1], color[2], color[3], 0.35)
  f.portraitBorder:SetDrawLayer("BACKGROUND")

  -- CC overlay over the portrait
  f.cc = CreateFrame("Frame", nil, f); f.cc:SetAllPoints(f.portrait); f.cc:SetFrameLevel(f:GetFrameLevel() + 3)
  f.cc.icon = f.cc:CreateTexture(nil, "ARTWORK"); f.cc.icon:SetAllPoints(); f.cc.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  f.cc.border = f.cc:CreateTexture(nil, "OVERLAY"); f.cc.border:SetPoint("TOPLEFT", -2, 2); f.cc.border:SetPoint("BOTTOMRIGHT", 2, -2); f.cc.border:SetTexture(1, 0.1, 0.1, 0.9); f.cc.border:SetDrawLayer("BORDER")
  f.cc.text = f.cc:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"); f.cc.text:SetPoint("CENTER"); f.cc.text:SetTextColor(1, 1, 1)
  f.cc:Hide()

  -- name / spec
  f.name = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  f.spec = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.spec:SetTextColor(0.8, 0.8, 0.8)
  local barX = left and 70 or 8
  local barW = FRAME_W - 78
  if left then f.name:SetPoint("TOPLEFT", f, "TOPLEFT", barX, -8); f.spec:SetPoint("TOPRIGHT", f, "TOPRIGHT", -8, -11)
  else f.name:SetPoint("TOPRIGHT", f, "TOPRIGHT", -70, -8); f.spec:SetPoint("TOPLEFT", f, "TOPLEFT", 8, -11) end

  -- health
  f.hp = CreateFrame("StatusBar", nil, f); f.hp:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
  f.hp:SetPoint("TOPLEFT", f, "TOPLEFT", barX, -28); f.hp:SetWidth(barW); f.hp:SetHeight(18); f.hp:SetMinMaxValues(0, 1)
  f.hp.bg = f.hp:CreateTexture(nil, "BACKGROUND"); f.hp.bg:SetAllPoints(); f.hp.bg:SetTexture(0.25, 0.05, 0.05, 0.8)
  f.hp.text = f.hp:CreateFontString(nil, "OVERLAY", "GameFontHighlight"); f.hp.text:SetPoint("CENTER")
  f.hp.pct = f.hp:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.hp.pct:SetPoint("RIGHT", f.hp, "RIGHT", -4, 0)
  -- power
  f.pw = CreateFrame("StatusBar", nil, f); f.pw:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
  f.pw:SetPoint("TOPLEFT", f.hp, "BOTTOMLEFT", 0, -1); f.pw:SetWidth(barW); f.pw:SetHeight(7); f.pw:SetMinMaxValues(0, 1)
  f.pw.bg = f.pw:CreateTexture(nil, "BACKGROUND"); f.pw.bg:SetAllPoints(); f.pw.bg:SetTexture(0, 0, 0, 0.6)
  -- cast bar
  f.cast = CreateFrame("StatusBar", nil, f); f.cast:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar"); f.cast:SetStatusBarColor(1, 0.7, 0)
  f.cast:SetPoint("TOPLEFT", f.pw, "BOTTOMLEFT", 18, -2); f.cast:SetWidth(barW - 18); f.cast:SetHeight(16); f.cast:SetMinMaxValues(0, 1)
  f.cast.bg = f.cast:CreateTexture(nil, "BACKGROUND"); f.cast.bg:SetAllPoints(); f.cast.bg:SetTexture(0, 0, 0, 0.6)
  f.cast.icon = f.cast:CreateTexture(nil, "ARTWORK"); f.cast.icon:SetWidth(16); f.cast.icon:SetHeight(16); f.cast.icon:SetPoint("RIGHT", f.cast, "LEFT", -1, 0); f.cast.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  f.cast.text = f.cast:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.cast.text:SetPoint("LEFT", f.cast, "LEFT", 3, 0)
  f.cast.time = f.cast:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.cast.time:SetPoint("RIGHT", f.cast, "RIGHT", -3, 0)
  f.cast:Hide()

  -- aura row (debuffs/buffs) under the portrait
  f.auras = {}
  for k = 1, 8 do
    local a = CreateFrame("Frame", nil, f); a:SetWidth(18); a:SetHeight(18)
    if left then a:SetPoint("TOPLEFT", f, "TOPLEFT", 8 + (k - 1) * 19, -66) else a:SetPoint("TOPRIGHT", f, "TOPRIGHT", -8 - (k - 1) * 19, -66) end
    a.icon = a:CreateTexture(nil, "ARTWORK"); a.icon:SetAllPoints(); a.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    a.border = a:CreateTexture(nil, "BORDER"); a.border:SetPoint("TOPLEFT", -1, 1); a.border:SetPoint("BOTTOMRIGHT", 1, -1)
    a.text = a:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); a.text:SetPoint("BOTTOM", a, "BOTTOM", 0, -2)
    a:Hide(); f.auras[k] = a
  end

  -- recent abilities row (newest nearest the centre of the screen)
  f.hist = {}
  for k = 1, 7 do
    local h = CreateFrame("Frame", nil, f); h:SetWidth(24); h:SetHeight(24)
    if left then h:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8 - (k - 1) * 26, 32) else h:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 8 + (k - 1) * 26, 32) end
    h.icon = h:CreateTexture(nil, "ARTWORK"); h.icon:SetAllPoints(); h.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    h:Hide(); f.hist[k] = h
  end
  f.histLabel = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.histLabel:SetTextColor(0.6, 0.6, 0.6); f.histLabel:SetText("casts")
  if left then f.histLabel:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 8, 36) else f.histLabel:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8, 36) end

  -- cooldown tracker row
  f.cds = {}
  for k = 1, 10 do
    local c = CreateFrame("Frame", nil, f); c:SetWidth(24); c:SetHeight(24)
    if left then c:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 8 + (k - 1) * 26, 6) else c:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8 - (k - 1) * 26, 6) end
    c.icon = c:CreateTexture(nil, "ARTWORK"); c.icon:SetAllPoints(); c.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    c.cd = CreateFrame("Cooldown", nil, c, "CooldownFrameTemplate"); c.cd:SetAllPoints()
    c.text = c:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); c.text:SetPoint("CENTER")
    c:Hide(); f.cds[k] = c
  end

  -- dead overlay
  f.deadTex = f:CreateTexture(nil, "OVERLAY"); f.deadTex:SetAllPoints(f); f.deadTex:SetTexture(0, 0, 0, 0.55); f.deadTex:Hide()
  f.dead = f:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge"); f.dead:SetPoint("CENTER", f, "CENTER", 0, 10); f.dead:SetText("DEAD"); f.dead:SetTextColor(1, 0.25, 0.25); f.dead:Hide()

  -- target line
  f.target = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.target:SetTextColor(1, 0.9, 0.5)
  if left then f.target:SetPoint("TOPRIGHT", f.pw, "BOTTOMRIGHT", 0, -20) else f.target:SetPoint("TOPLEFT", f.pw, "BOTTOMLEFT", 0, -20) end

  f:SetScript("OnClick", function(self) if self.idx then cmd(".botarena cam " .. self.idx) end end)
  f:SetScript("OnEnter", function(self) GameTooltip:SetOwner(self, left and "ANCHOR_RIGHT" or "ANCHOR_LEFT"); GameTooltip:SetText("Click: camera on " .. (self.botName or "bot")); GameTooltip:Show() end)
  f:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f:Hide()
  return f
end
for i = 1, 5 do frames.A[i] = makeBotFrame("A", i); frames.H[i] = makeBotFrame("H", i) end

-- ------------------------------------------------------------------ ability ticker (bottom centre)
local ticker = CreateFrame("Frame", nil, root)
ticker:SetWidth(520); ticker:SetHeight(150); ticker:SetPoint("BOTTOM", root, "BOTTOM", 0, 120)
ticker.lines = {}
for k = 1, 7 do
  local l = CreateFrame("Frame", nil, ticker); l:SetWidth(520); l:SetHeight(20); l:SetPoint("BOTTOM", ticker, "BOTTOM", 0, (k - 1) * 21)
  l.icon = l:CreateTexture(nil, "ARTWORK"); l.icon:SetWidth(18); l.icon:SetHeight(18); l.icon:SetPoint("CENTER", l, "CENTER", -60, 0); l.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  l.caster = l:CreateFontString(nil, "OVERLAY", "GameFontNormal"); l.caster:SetPoint("RIGHT", l.icon, "LEFT", -6, 0)
  l.spell = l:CreateFontString(nil, "OVERLAY", "GameFontHighlight"); l.spell:SetPoint("LEFT", l.icon, "RIGHT", 6, 0)
  l.target = l:CreateFontString(nil, "OVERLAY", "GameFontNormal"); l.target:SetPoint("LEFT", l.spell, "RIGHT", 8, 0)
  l:Hide(); ticker.lines[k] = l
end

-- ------------------------------------------------------------------ control panel
local panel = CreateFrame("Frame", "BotArenaPanel", UIParent)
panel:SetWidth(300); panel:SetHeight(360); panel:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
panel:SetFrameStrata("DIALOG"); panel:SetMovable(true); panel:EnableMouse(true); panel:RegisterForDrag("LeftButton")
panel:SetScript("OnDragStart", panel.StartMoving); panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
panel:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background", edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 32, insets = { left = 11, right = 12, top = 12, bottom = 11 } })
panel:Hide()
local ptitle = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge"); ptitle:SetPoint("TOP", panel, "TOP", 0, -16); ptitle:SetText("BotArena Control")
local pclose = CreateFrame("Button", nil, panel, "UIPanelCloseButton"); pclose:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -6, -6)

local sel = { arena = "random", type = "3", compA = "random", compH = "random" }

local function makeDropdown(name, label, y, items, key, filterByType)
  local lbl = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall"); lbl:SetPoint("TOPLEFT", panel, "TOPLEFT", 24, y); lbl:SetText(label)
  local dd = CreateFrame("Frame", name, panel, "UIDropDownMenuTemplate")
  dd:SetPoint("TOPLEFT", panel, "TOPLEFT", 90, y + 8)
  UIDropDownMenu_SetWidth(dd, 160)
  UIDropDownMenu_Initialize(dd, function()
    for _, it in ipairs(items) do
      if not filterByType or it[3] == 0 or tostring(it[3]) == sel.type then
        local info = UIDropDownMenu_CreateInfo()
        info.text = it[2]; info.value = it[1]; info.checked = (sel[key] == it[1])
        info.func = function() sel[key] = it[1]; UIDropDownMenu_SetText(dd, it[2]) end
        UIDropDownMenu_AddButton(info)
      end
    end
  end)
  UIDropDownMenu_SetText(dd, items[1][2])
  return dd
end
local ddType = makeDropdown("BotArenaDDType", "Bracket", -48, TYPES, "type")
local ddArena = makeDropdown("BotArenaDDArena", "Arena", -82, ARENAS, "arena")
local ddA = makeDropdown("BotArenaDDA", "Gold team", -116, PRESETS, "compA", true)
local ddH = makeDropdown("BotArenaDDH", "Green team", -150, PRESETS, "compH", true)
UIDropDownMenu_SetText(ddType, "3v3")

local function makeButton(text, x, y, w, onClick)
  local b = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate"); b:SetWidth(w); b:SetHeight(24); b:SetPoint("TOPLEFT", panel, "TOPLEFT", x, y); b:SetText(text); b:SetScript("OnClick", onClick); return b
end
makeButton("Start match", 24, -190, 124, function()
  cmd((".botarena start %s %s %s %s"):format(sel.type, sel.arena, sel.compA, sel.compH))
end)
makeButton("Stop", 152, -190, 124, function() cmd(".botarena stop") end)
makeButton("Spectate (teleport)", 24, -220, 124, function() cmd(".botarena spectate") end)
makeButton("Camera: auto", 152, -220, 124, function() cmd(".botarena cam auto") end)
makeButton("Camera: free", 24, -250, 124, function() cmd(".botarena cam off") end)
makeButton("Auto rotation on", 152, -250, 124, function() cmd(".botarena auto on 20") end)
makeButton("Auto rotation off", 24, -280, 124, function() cmd(".botarena auto off") end)
makeButton("Toggle game UI", 152, -280, 124, function() SlashCmdList["BOTARENA"]("ui") end)
makeButton("Unattended: on", 24, -310, 124, function() setAutoSpectate(true); db.autoUI = true; cmd(".botarena auto on 20") end)
makeButton("Unattended: off", 152, -310, 124, function() setAutoSpectate(false); db.autoUI = false; cmd(".botarena auto off") end)
local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); hint:SetPoint("BOTTOM", panel, "BOTTOM", 0, 16); hint:SetText("/ba panel toggles this window")

-- small launcher button (top-left) to open the panel
local launcher = CreateFrame("Button", nil, root, "UIPanelButtonTemplate")
launcher:SetWidth(70); launcher:SetHeight(20); launcher:SetPoint("TOPLEFT", root, "TOPLEFT", 14, -6); launcher:SetText("BotArena")
launcher:SetScript("OnClick", function() if panel:IsShown() then panel:Hide() else panel:Show() end end)

-- ------------------------------------------------------------------ rendering
local function applyClassIcon(tex, cls)
  local coords = CLASS_ICON_TCOORDS[CLASS_TOKENS[cls] or ""]
  if coords then tex:SetTexCoord(unpack(coords)) else tex:SetTexCoord(0, 1, 0, 1) end
end

local function renderBot(f, b)
  f.idx = b.idx; f.botName = b.name
  applyClassIcon(f.portrait, b.cls)
  local r, g, bl = classColor(b.cls)
  f.name:SetText(b.name); f.name:SetTextColor(r, g, bl)
  f.spec:SetText((SPEC_NAMES[b.spec] or "") .. " " .. (CLASS_NAMES[b.cls] or ""))
  local pct = (b.maxhp > 0) and (b.hp / b.maxhp) or 0
  f.hp:SetValue(pct); f.hp:SetStatusBarColor(0.15 + (1 - pct) * 0.8, 0.2 + pct * 0.7, 0.15)
  f.hp.text:SetText(fmt(b.hp) .. " / " .. fmt(b.maxhp)); f.hp.pct:SetText(math.floor(pct * 100 + 0.5) .. "%")
  local pc = POWER_COLORS[b.ptype] or { 0.5, 0.5, 0.5 }
  f.pw:SetStatusBarColor(pc[1], pc[2], pc[3]); f.pw:SetValue((b.maxpw > 0) and (b.pw / b.maxpw) or 0)
  f.target:SetText(b.target ~= "" and (">> " .. b.target) or "")
  if b.alive == 0 then f.deadTex:Show(); f.dead:Show(); f.cast:Hide(); f.cc:Hide() else f.deadTex:Hide(); f.dead:Hide() end
  -- cast bar (interpolated in OnUpdate)
  if b.alive == 1 and b.castId > 0 and b.castTotal > 0 then
    f.castData = b
    f.cast.icon:SetTexture(spellIcon(b.castId)); f.cast.text:SetText(spellName(b.castId)); f.cast:Show()
  else
    f.castData = nil; f.cast:Hide()
  end
  -- auras
  local list = state.auras[b.idx] or {}
  local ccBest
  local n = 0
  for _, a in ipairs(list) do
    if a.flag == "c" and (not ccBest or a.left > ccBest.left) then ccBest = a end
    if a.flag ~= "c" and n < 8 then
      n = n + 1
      local af = f.auras[n]
      af.icon:SetTexture(spellIcon(a.id))
      if a.flag == "d" then af.border:SetTexture(0.9, 0.2, 0.2, 0.9) else af.border:SetTexture(0.2, 0.9, 0.2, 0.9) end
      af.aura = a; af:Show()
    end
  end
  for k = n + 1, 8 do f.auras[k]:Hide(); f.auras[k].aura = nil end
  if ccBest and b.alive == 1 then f.cc.icon:SetTexture(spellIcon(ccBest.id)); f.cc.aura = ccBest; f.cc:Show() else f.cc:Hide(); f.cc.aura = nil end
  -- history
  local hl = history[b.idx] or {}
  for k = 1, 7 do
    local e = hl[#hl - k + 1]
    if e then f.hist[k].icon:SetTexture(spellIcon(e.id)); f.hist[k].t = e.t; f.hist[k]:Show() else f.hist[k]:Hide() end
  end
  -- cooldown tracker
  local cds = cooldowns[b.idx] or {}
  local sorted = {}
  for nm, c in pairs(cds) do sorted[#sorted + 1] = { nm, c } end
  table.sort(sorted, function(x, y) return x[2].start > y[2].start end)
  for k = 1, 10 do
    local c = sorted[k]
    if c then
      local cf = f.cds[k]; cf.icon:SetTexture(c[2].icon); cf.data = c[2]; cf:Show()
      CooldownFrame_SetTimer(cf.cd, c[2].start, c[2].dur, 1)
    else f.cds[k]:Hide(); f.cds[k].data = nil end
  end
  f:Show()
end

local function render()
  hideWorldState()
  local ia, ih, aliveA, aliveH = 0, 0, 0, 0
  for i = 1, 5 do frames.A[i]:Hide(); frames.H[i]:Hide() end
  for _, b in ipairs(state.bots) do
    if b.team == "A" then ia = ia + 1; if ia <= 5 then renderBot(frames.A[ia], b) end; if b.alive == 1 then aliveA = aliveA + 1 end
    else ih = ih + 1; if ih <= 5 then renderBot(frames.H[ih], b) end; if b.alive == 1 then aliveH = aliveH + 1 end end
  end
  local s = state.status
  if s.state then
    local arenaName = ({ [559] = "NAGRAND ARENA", [562] = "BLADE'S EDGE ARENA", [572] = "RUINS OF LORDAERON", [617] = "DALARAN SEWERS", [618] = "RING OF VALOR" })[s.mapId or 0] or "ARENA"
    top.arena:SetText(arenaName .. "   " .. (s.type or 3) .. "v" .. (s.type or 3) .. "   match #" .. (s.match or "?"))
    top.goldAlive:SetText(string.rep("|cff00ff00*|r ", aliveA) .. string.rep("|cff666666x|r ", math.max(0, (s.type or 3) - aliveA)))
    top.greenAlive:SetText(string.rep("|cff00ff00*|r ", aliveH) .. string.rep("|cff666666x|r ", math.max(0, (s.type or 3) - aliveH)))
    local phase = (s.bgStatus == 2 and "PREPARATION") or (s.bgStatus == 3 and "FIGHT") or (s.bgStatus == 4 and "MATCH OVER") or s.state
    top.phase:SetText(phase)
    if s.winner == "A" then banner:SetText("GOLD TEAM WINS"); banner:SetTextColor(unpack(GOLD)); banner:Show()
    elseif s.winner == "H" then banner:SetText("GREEN TEAM WINS"); banner:SetTextColor(unpack(GREEN)); banner:Show()
    elseif s.bgStatus == 2 then banner:SetText("GATES OPEN IN " .. math.max(0, 60 - (s.elapsed or 0)) .. "s"); banner:SetTextColor(1, 1, 1); banner:Show()
    else banner:Hide() end
  end
  -- ticker
  local ev = state.events
  for k = 1, 7 do
    local e = ev[#ev - k + 1]
    local l = ticker.lines[k]
    if e then
      local cb = state.bots[e.caster]; local tb = state.bots[e.target]
      l.icon:SetTexture(spellIcon(e.spell))
      l.caster:SetText(cb and cb.name or "?"); if cb then l.caster:SetTextColor(unpack(teamColor(cb.team))) end
      l.spell:SetText(spellName(e.spell))
      if tb and tb ~= cb then l.target:SetText("-> " .. tb.name); l.target:SetTextColor(unpack(teamColor(tb.team))) else l.target:SetText("") end
      l:SetAlpha(math.max(0.25, 1 - (k - 1) * 0.12)); l.t = e.t; l:Show()
    else l:Hide() end
  end
end

-- per-frame updates: cast bar interpolation, CC/aura countdowns, cooldown numbers, event fading
root:SetScript("OnUpdate", function(self, elapsed)
  local now = GetTime()
  for _, team in pairs(frames) do
    for _, f in ipairs(team) do
      if f:IsShown() then
        local b = f.castData
        if b then
          local left = b.castLeft / 1000 - (now - b.recv)
          if left <= 0 then f.cast:Hide(); f.castData = nil else
            f.cast:SetValue(1 - left / (b.castTotal / 1000)); f.cast.time:SetText(string.format("%.1f", left))
          end
        end
        if f.cc.aura then
          local left = f.cc.aura.left / 1000 - (now - f.cc.aura.recv)
          if left <= 0 then f.cc:Hide(); f.cc.aura = nil else f.cc.text:SetText(string.format("%.0f", left)) end
        end
        for _, af in ipairs(f.auras) do
          if af.aura then
            local left = af.aura.left / 1000 - (now - af.aura.recv)
            if left <= 0 then af:Hide(); af.aura = nil else af.text:SetText(left < 10 and string.format("%.0f", left) or "") end
          end
        end
        for _, cf in ipairs(f.cds) do
          if cf.data then
            local left = cf.data.start + cf.data.dur - now
            if left <= 0 then cf.text:SetText(""); cf.icon:SetVertexColor(1, 1, 1) else cf.icon:SetVertexColor(0.5, 0.5, 0.5); cf.text:SetText(left >= 60 and string.format("%dm", math.floor(left / 60)) or string.format("%d", math.ceil(left))) end
          end
        end
        for _, h in ipairs(f.hist) do if h:IsShown() and h.t then h:SetAlpha(math.max(0.3, 1 - (now - h.t) / 20)) end end
      end
    end
  end
  if state.status.elapsed and lastSnapshot > 0 then
    local el = state.status.elapsed + (now - lastSnapshot)
    top.timer:SetText(string.format("%02d:%02d", math.floor(el / 60), math.floor(el % 60)))
  end
end)

-- ------------------------------------------------------------------ feed parsing
local function onMessage(msg)
  local f = split(msg, ";")
  if f[1] == "S" then
    state.status = { state = f[2], elapsed = tonumber(f[3]) or 0, type = tonumber(f[4]), winner = f[5], mapId = tonumber(f[6]), match = f[7], bgStatus = tonumber(f[8]) }
    state.bots = {}
    lastSnapshot = GetTime()
    if state.status.match ~= state.lastMatch then
      state.lastMatch = state.status.match; history = {}; cooldowns = {}; state.events = {}; state.auras = {}
    end
    render()
  elseif f[1] == "B" then
    local b = { idx = tonumber(f[2]), team = f[3], name = f[4], cls = tonumber(f[5]), spec = tonumber(f[6]),
      hp = tonumber(f[7]) or 0, maxhp = tonumber(f[8]) or 0, pw = tonumber(f[9]) or 0, maxpw = tonumber(f[10]) or 0,
      ptype = tonumber(f[11]) or 0, alive = tonumber(f[12]) or 1, target = f[13] or "", castId = tonumber(f[14]) or 0,
      castLeft = tonumber(f[15]) or 0, castTotal = tonumber(f[16]) or 0, recv = GetTime() }
    state.bots[b.idx] = b
    render()
  elseif f[1] == "A" then
    local idx = tonumber(f[2]); local list = {}
    for _, item in ipairs(split(f[3] or "", ",")) do
      local id, ms, flag = item:match("^(%d+):(%-?%d+):(%a)$")
      if id then list[#list + 1] = { id = tonumber(id), left = tonumber(ms), flag = flag, recv = GetTime() } end
    end
    state.auras[idx] = list
    render()
  elseif f[1] == "E" then
    local seq = tonumber(f[2]); local caster = tonumber(f[3]); local spell = tonumber(f[4]); local target = tonumber(f[5]); local age = (tonumber(f[6]) or 0) / 1000
    if seq and seq > state.lastSeq then
      state.lastSeq = seq
      local t = GetTime() - age
      state.events[#state.events + 1] = { seq = seq, caster = caster, spell = spell, target = target, t = t }
      if #state.events > 30 then table.remove(state.events, 1) end
      history[caster] = history[caster] or {}
      local h = history[caster]; h[#h + 1] = { id = spell, t = t }; if #h > 12 then table.remove(h, 1) end
      local nm = GetSpellInfo(spell)
      local cd = nm and COOLDOWNS[nm]
      if cd and cd > 0 then cooldowns[caster] = cooldowns[caster] or {}; cooldowns[caster][nm] = { icon = spellIcon(spell), start = t, dur = cd } end
      render()
    end
  end
end

-- Unattended mode: when enabled, the character spectates every match automatically (auto camera, UI hidden).
local autoTimer = 0
local autoFrame = CreateFrame("Frame")
autoFrame:Hide()
autoFrame:SetScript("OnUpdate", function(self, elapsed)
  autoTimer = autoTimer + elapsed
  if autoTimer < 5 then return end
  autoTimer = 0
  if not db.autoSpectate then self:Hide(); return end
  local s = state.status
  local inArena = (select(2, IsInInstance()) == "arena")
  -- no feed yet (not registered as spectator) or a match is running while we are outside: (re)join it
  if (not s.state or s.state ~= "idle") and not inArena then
    cmd(".botarena spectate"); cmd(".botarena cam auto")
  end
end)
local function setAutoSpectate(on)
  db.autoSpectate = on
  if on then autoTimer = 4; autoFrame:Show() else autoFrame:Hide() end
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("ADDON_LOADED"); ev:RegisterEvent("CHAT_MSG_ADDON"); ev:RegisterEvent("PLAYER_LOGIN"); ev:RegisterEvent("PLAYER_ENTERING_WORLD")
ev:SetScript("OnEvent", function(self, event, prefix, msg)
  if event == "ADDON_LOADED" and prefix == "BotArenaSpectator" then
    -- Saved variables replace the file-scope table after the addon code runs.
    db = BotArenaSpectatorDB
  elseif event == "PLAYER_LOGIN" then
    -- Keep the viewer's angle when following or switching bots. Never re-zoom on selection.
    SetCVar("cameraSmoothStyle", 0)
    SetCVar("cameraSmoothTrackingStyle", 0)
    SetCVar("cameraTerrainTilt", 0)
    SetCVar("cameraBobbing", 0)
    SetCVar("cameraPivot", 0)
    DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99BotArena Spectator|r loaded: /ba panel to control matches, /ba for help.")
    if db.hidden then root:Hide() end
    -- unattended by default: a fresh profile goes straight into the running match (/ba autospec off to disable)
    if db.autoSpectate == nil then db.autoSpectate = true; db.autoUI = true end
    if db.autoSpectate then setAutoSpectate(true) end
  elseif event == "PLAYER_ENTERING_WORLD" then
    -- the server keeps streaming only to registered spectators; ask for the state so auto mode can react
    if db.autoSpectate then autoTimer = 4; autoFrame:Show() end
    if db.autoUI and UIParent:IsShown() and select(2, IsInInstance()) == "arena" then SlashCmdList["BOTARENA"]("ui") end
  elseif event == "CHAT_MSG_ADDON" and prefix == PREFIX then onMessage(msg) end
end)

-- ------------------------------------------------------------------ slash commands
SLASH_BOTARENA1 = "/ba"; SLASH_BOTARENA2 = "/botarena"
SlashCmdList["BOTARENA"] = function(input)
  local a, rest = (input or ""):match("^(%S*)%s*(.-)$"); a = (a or ""):lower()
  if a == "panel" then if panel:IsShown() then panel:Hide() else panel:Show() end
  elseif a == "hide" then root:Hide(); db.hidden = true; hideWorldState()
  elseif a == "show" then root:Show(); db.hidden = false; hideWorldState()
  elseif a == "cam" then cmd(".botarena cam " .. rest)
  elseif a == "spectate" then cmd(".botarena spectate")
  elseif a == "start" then cmd(".botarena start " .. rest)
  elseif a == "stop" then cmd(".botarena stop")
  elseif a == "auto" then cmd(".botarena auto " .. rest)
  elseif a == "status" then cmd(".botarena status")
  elseif a == "autospec" then setAutoSpectate(rest == "on"); print("BotArena auto-spectate " .. (db.autoSpectate and "on" or "off"))
  elseif a == "autoui" then db.autoUI = (rest == "on"); print("BotArena auto-hide UI " .. (db.autoUI and "on" or "off"))
  elseif a == "ui" then
    if UIParent:IsShown() then root:SetParent(WorldFrame); root:SetScale(UIParent:GetEffectiveScale()); UIParent:Hide()
    else UIParent:Show(); root:SetParent(UIParent); root:SetScale(1) end
  else
    print("/ba panel | cam <1-10|name|auto|off> | spectate | start [3] [na] [compA] [compH] | stop | auto on|off | autospec on|off | autoui on|off | ui | hide | show")
  end
end
