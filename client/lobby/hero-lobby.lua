-- Full-viewport character selection, spectator setup and matchmaking controls.
local data,U=ArenaLobbyData,ArenaUI
local root=CreateFrame("Frame","ArenaLobby",GlueParent);root:SetSize(GetScreenWidth(),GetScreenHeight());root:SetPoint("CENTER",GlueParent,"CENTER");root:SetFrameStrata("FULLSCREEN_DIALOG");root:EnableMouse(true)
for _,f in ipairs({GlueParent:GetChildren()})do if f~=root then f:Hide()end end
local bg=root:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints(root);bg:SetTexture(.025,.02,.015,1)
local stage=CreateFrame("ModelFFX","ArenaHeroModel",root);stage:SetAllPoints(root);stage:SetFrameLevel(1)
SetCharCustomizeFrame("ArenaHeroModel");ResetCharCustomize();ArenaHeroScale=.76
local layout=CreateFrame("Frame",nil,root);layout:SetSize(GetScreenWidth(),GetScreenHeight());layout:SetPoint("CENTER",root,"CENTER");layout:SetFrameLevel(20)
local w,h=GetScreenWidth(),GetScreenHeight()
local selected,mode,size,arena=1,"bots",2,"random"
local savedName=nil;local existingIndex=0
local header=CreateFrame("Frame",nil,layout);header:SetSize(w-32,72);header:SetPoint("TOPLEFT",16,-10)
U.text(header,"ARENA",27,20,-12,300):SetTextColor(1,.82,0)
U.text(header,"WRATH OF THE LICH KING · SEASON 8",11,22,-44,360)
ArenaModeButtons={}
local modes={{"watch","Spectate"},{"bots","Play with bots"},{"players","Matchmaking"}}
local left=U.panel(layout,200,530,18,-105)
U.text(left,"CHAMPIONS",17,16,-17,175):SetTextColor(1,.82,0)
ArenaHeroButtons={}
local heroTitle=U.text(layout,"",22,w/2-180,-100,360);heroTitle:SetJustifyH("CENTER");heroTitle:SetTextColor(1,.82,0)
local heroSpec=U.text(layout,"",12,w/2-200,-130,400);heroSpec:SetJustifyH("CENTER")
local bottom=CreateFrame("Frame",nil,layout);bottom:SetSize(w-32,88);bottom:SetPoint("TOPLEFT",16,-h+100)
U.text(bottom,"Character name",12,18,-13,180)
local name=CreateFrame("EditBox","ArenaHeroName",bottom);name:SetSize(180,28);name:SetPoint("TOPLEFT",18,-36);name:SetFont("Fonts\\FRIZQT__.TTF",14);name:SetAutoFocus(false);name:SetMaxLetters(12)
name:SetBackdrop({bgFile="Interface\\Tooltips\\UI-Tooltip-Background",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=true,tileSize=16,edgeSize=12});name:SetTextInsets(8,8,0,0);name:SetScript("OnEscapePressed",function()name:ClearFocus()end)
U.button(bottom,"Random",86,28,205,-36,function()
 local a={"Ash","Val","Thal","Nor","Zen","Kae"};local b={"rion","dren","lith","wyn","thas","mar"};savedName=nil;name:SetText(a[math.random(#a)]..b[math.random(#b)]..string.char(math.random(97,122)))
end)
local status=U.text(layout,"",13,w-290,-363,260);ArenaLobbyStatus=status
local matchmaking=U.panel(layout,260,240,w-278,-105);ArenaMatchmakingPanel=matchmaking
U.text(matchmaking,"ARENA MATCHMAKING",17,16,-18,230):SetTextColor(1,.82,0)
local matchText=U.text(matchmaking,"",13,16,-55,228);matchText:SetHeight(150);matchText:SetJustifyV("TOP")
local inspector=U.inspect(layout,function()return data.builds[selected]end)
ArenaGearButton=U.button(left,"Equipment",168,30,16,-448,function()if inspector.gear:IsShown()then inspector.gear:Hide()else inspector.gear:Show()end end)
ArenaTalentButton=U.button(left,"Talents & Glyphs",168,30,16,-482,function()inspector.talents()end)
local spectator=U.panel(layout,660,450,w/2-330,-h/2+210);ArenaSpectatorSettings=spectator
U.text(spectator,"SPECTATE AN ARENA",25,28,-25,600):SetTextColor(1,.82,0)
U.text(spectator,"Start a bot match and follow the action.",14,30,-68,600)
U.text(spectator,"MATCH FORMAT",14,30,-116,560):SetTextColor(1,.82,0)
U.text(spectator,"BATTLEGROUND",14,30,-211,560):SetTextColor(1,.82,0)
local spectatorInfo=U.text(spectator,"",13,30,-310,600);spectatorInfo:SetHeight(75);spectatorInfo:SetJustifyV("TOP")
local specStatus=U.text(spectator,"",12,30,-390,370)
local sizeButtons={};local arenaButtons={};ArenaSizeButtons={};ArenaMapButtons=arenaButtons
local function updateOptions()
 for _,entry in ipairs(sizeButtons)do entry.button.caption:SetTextColor(size==entry.size and 1 or .8,size==entry.size and .82 or .8,size==entry.size and 0 or .8)end
 for key,b in pairs(arenaButtons)do b.caption:SetTextColor(key==arena and 1 or .8,key==arena and .82 or .8,key==arena and 0 or .8)end
 matchText:SetText(mode=="players" and (size.."v"..size.." · Players only\n\nChoose your champion, then join the queue.\n\n"..(size*2).." players required\nHealers distributed between teams.") or (size.."v"..size.." · Bot teammates\n\nEnter with your chosen champion. Bots fill the remaining places."))
 spectatorInfo:SetText((size==2 and "Arms Warrior / Holy Paladin" or "Arms Warrior / Unholy Death Knight / Holy Paladin").." on both teams.\n\nFollow the first Gold fighter. Camera switching stays manual.")
end
for _,s in ipairs({2,3})do
 local n=s
 local a=U.button(spectator,s.."v"..s,130,38,30+(s-2)*145,-148,function()size=n;updateOptions()end);table.insert(sizeButtons,{size=s,button=a});ArenaSizeButtons[s]=a
 local b=U.button(matchmaking,s.."v"..s,100,32,16+(s-2)*120,-190,function()size=n;updateOptions()end);table.insert(sizeButtons,{size=s,button=b})
end
for i,m in ipairs({{"random","Random"},{"na","Nagrand"},{"be","Blade's Edge"},{"rl","Lordaeron"}})do local key=m[1];arenaButtons[key]=U.button(spectator,m[2],140,34,30+(i-1)*147,-245,function()arena=key;updateOptions()end)end
local function selectHero(i,keep)
 selected=i;local b=data.builds[i];ArenaSelectedBuild=b.id
 if not keep then savedName=nil;existingIndex=0;name:SetText("")end
 for n,btn in ipairs(ArenaHeroButtons)do btn.caption:SetTextColor(n==i and 1 or .85,n==i and .82 or .85,n==i and 0 or .85)end
 local races={GetAvailableRaces()};for n=1,#races,3 do if string.upper(races[n+1])==b.raceToken then SetSelectedRace((n+2)/3)end end
 SetSelectedSex(2)
 local classes={GetAvailableClasses()};for n=1,#classes,3 do if string.upper(classes[n+1])==b.classToken then SetSelectedClass((n+2)/3)end end
 SetCharCustomizeBackground("Interface\\Glues\\Models\\UI_"..b.scene.."\\UI_"..b.scene..".m2");ArenaHeroPreview=b.previewJson
 heroTitle:SetText(b.className);heroSpec:SetText(b.spec.." · "..b.role.." · Level 80");inspector.refresh()
end
for i,b in ipairs(data.builds)do local n=i;ArenaHeroButtons[i]=U.button(left,b.className,168,32,16,-48-(i-1)*39,function()selectHero(n)end)end
ArenaSavedButton=U.button(bottom,"Saved characters",165,30,315,-35,function()
 if #data.characters==0 then status:SetText("No saved characters yet");return end
 existingIndex=existingIndex%#data.characters+1;local c=data.characters[existingIndex]
 for i,b in ipairs(data.builds)do if b.id==c.build then selectHero(i,true)end end
 savedName=c.name;name:SetText(c.name)
end)
local function launch()
 if ArenaLobbyBusy then return end
 name:ClearFocus();ArenaLobbyBusy=true;status:SetText("Preparing...");specStatus:SetText("Preparing spectator camera...")
 ArenaLobbyRequest={action="play",build=data.builds[selected].id,name=mode=="watch" and "" or name:GetText(),existing=savedName==name:GetText() and savedName or "",mode=mode,size=size,arena=arena}
end
ArenaLaunchButton=U.button(bottom,"ENTER ARENA",230,42,w-300,-25,launch)
ArenaWatchButton=U.button(spectator,"WATCH MATCH",210,42,420,-385,launch)
local rotate=CreateFrame("Frame",nil,layout);rotate:SetSize(260,34);rotate:SetPoint("BOTTOM",layout,"BOTTOM",0,170)
U.text(rotate,"Drag hero to rotate",11,45,-10,170):SetJustifyH("CENTER")
stage:EnableMouse(true);local drag=false;local lastX=0
local function beginDrag(_,button)if button=="LeftButton"then drag=true;lastX=GetCursorPosition()end end
local function endDrag()drag=false end
root:SetScript("OnMouseDown",beginDrag);root:SetScript("OnMouseUp",endDrag)
stage:SetScript("OnMouseDown",beginDrag)
stage:SetScript("OnMouseUp",endDrag)
stage:SetScript("OnHide",function()drag=false end)
root:SetScript("OnUpdate",function()
 if drag then local x=GetCursorPosition();SetCharacterCreateFacing(GetCharacterCreateFacing()+(x-lastX)*.4);lastX=x end
end)
local function modeSelect(m)
 mode=m;ArenaLobbyMode=m;ArenaLobbyBusy=false;status:SetText("");specStatus:SetText("");inspector.modal:Hide()
 for key,b in pairs(ArenaModeButtons)do b.caption:SetTextColor(key==m and 1 or .8,key==m and .82 or .8,key==m and 0 or .8)end
 if m=="watch"then stage:Hide();left:Hide();bottom:Hide();heroTitle:Hide();heroSpec:Hide();rotate:Hide();matchmaking:Hide();inspector.hide();spectator:Show()
 else stage:Show();left:Show();bottom:Show();heroTitle:Show();heroSpec:Show();rotate:Show();matchmaking:Show();inspector.gear:Show();spectator:Hide()end
 ArenaLaunchButton.caption:SetText(m=="players" and "JOIN QUEUE" or "ENTER ARENA");updateOptions()
end
for i,m in ipairs(modes)do local key=m[1];ArenaModeButtons[key]=U.button(header,m[2],155,34,w-540+(i-1)*166,-20,function()modeSelect(key)end)end
function ArenaLobbySnapshot()return selected,mode,size,arena,name:GetText(),savedName end
function ArenaLobbyError(text)ArenaLobbyBusy=false;status:SetText(text);specStatus:SetText(text)end
function ArenaLobbyTakeRequest()local r=ArenaLobbyRequest;ArenaLobbyRequest=nil;if r then return r.action,r.build,r.name,r.existing,r.mode,r.size,r.arena end end
function ArenaLobbyHide()root:Hide();ArenaHeroPreview=nil;ArenaHeroScale=nil end
local restore=ArenaLobbyRestore or {}
size=restore[3] or 2;arena=restore[4] or "random"
selectHero(restore[1] or 1);modeSelect(restore[2] or "bots")
name:SetText(restore[5] or "");savedName=restore[6]
