-- In-game match transitions and a character-selection view while matchmaking.
local U=ArenaUI
local root=CreateFrame("Frame","ArenaWorldControls",WorldFrame);root:SetSize(GetScreenWidth(),GetScreenHeight());root:SetPoint("CENTER",WorldFrame,"CENTER");root:SetFrameStrata("FULLSCREEN_DIALOG")
local cover=CreateFrame("Frame","ArenaWorldCover",root);cover:SetSize(GetScreenWidth(),GetScreenHeight());cover:SetPoint("CENTER",root,"CENTER");cover:SetFrameLevel(root:GetFrameLevel()+1);cover:EnableMouse(true);cover:EnableKeyboard(true)
cover:SetScript("OnMouseDown",function()end);cover:SetScript("OnMouseUp",function()end);cover:SetScript("OnKeyDown",function()end)
local bg=cover:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints(cover);bg:SetTexture(.025,.02,.015,1)
local text=U.text(cover,"Preparing...",22,0,0,700);text:ClearAllPoints();text:SetPoint("CENTER",0,25);text:SetJustifyH("CENTER");text:SetTextColor(1,.82,0)
local back=U.button(root,"Return to Lobby",165,34,root:GetWidth()-185,-18,function()ArenaWorldAction="back"end);back:SetFrameLevel(100);ArenaReturnButton=back
local queue=CreateFrame("Frame","ArenaQueueSelection",cover);queue:SetAllPoints(cover);queue:Hide()
local b=ArenaActiveBuild
local elapsed=0;local dots=0
if ArenaActiveMode=="players" then
 local scene=CreateFrame("Model",nil,queue);scene:SetAllPoints(queue);scene:SetModel("Interface\\Glues\\Models\\UI_"..b.scene.."\\UI_"..b.scene..".m2");scene:SetCamera(0)
 -- The client renders the stock paper-doll booth; borrow it while queued, then restore it.
 local model=CharacterModelFrame;ArenaQueuedHero=model
 local children={};for _,child in ipairs({model:GetChildren()})do if child:IsShown()then table.insert(children,child);child:Hide()end end
 local parent,oldW,oldH=model:GetParent(),model:GetWidth(),model:GetHeight();local points={}
 for i=1,model:GetNumPoints()do points[i]={model:GetPoint(i)}end
 local scripts={};for _,event in ipairs({"OnMouseDown","OnMouseUp","OnUpdate"})do scripts[event]=model:GetScript(event)end
 model:SetParent(queue);model:ClearAllPoints();model:SetSize(GetScreenWidth()*.42,GetScreenHeight()*.72);model:SetPoint("CENTER",queue,"CENTER",0,-25);model:SetUnit("player");model:SetModelScale(.76);model:SetFacing(0);model:EnableMouse(true);model:Show()
 queue:SetScript("OnHide",function()
  model:SetParent(parent);model:ClearAllPoints();model:SetSize(oldW,oldH);model:SetModelScale(1)
  for _,point in ipairs(points)do model:SetPoint(unpack(point))end
  for _,child in ipairs(children)do child:Show()end
  for _,event in ipairs({"OnMouseDown","OnMouseUp","OnUpdate"})do model:SetScript(event,scripts[event])end
 end)
 local drag=false;local lastX=0;model:SetScript("OnMouseDown",function(_,button)if button=="LeftButton"then drag=true;lastX=GetCursorPosition()end end);model:SetScript("OnMouseUp",function()drag=false end)
 model:SetScript("OnUpdate",function()if drag then local x=GetCursorPosition();model:SetFacing(model:GetFacing()+(x-lastX)*.008);lastX=x end end)
 local chrome=CreateFrame("Frame",nil,queue);chrome:SetAllPoints(queue);chrome:SetFrameLevel(20)
 local w,h=root:GetWidth(),root:GetHeight()
 local header=CreateFrame("Frame",nil,chrome);header:SetSize(w-32,72);header:SetPoint("TOPLEFT",16,-10)
 U.text(header,"ARENA MATCHMAKING",24,20,-18,w-240):SetTextColor(1,.82,0)
 local title=U.text(chrome,b.className,24,w/2-200,-100,400);title:SetJustifyH("CENTER");title:SetTextColor(1,.82,0)
 local spec=U.text(chrome,b.spec.." · "..b.role.." · "..ArenaActiveName,13,w/2-220,-134,440);spec:SetJustifyH("CENTER")
 local inspection=U.inspect(chrome,function()return b end)
 ArenaGearButton=U.button(chrome,"Equipment",175,32,24,-130,function()if inspection.gear:IsShown()then inspection.gear:Hide()else inspection.gear:Show()end end)
 ArenaTalentButton=U.button(chrome,"Talents & Glyphs",175,32,24,-170,inspection.talents)
 local panel=U.panel(chrome,270,300,w-290,-105);ArenaMatchmakingPanel=panel
 local search=U.text(panel,"FINDING PLAYERS",18,18,-22,234);search:SetTextColor(1,.82,0)
 local progress=U.text(panel,"",15,18,-69,234);progress:SetHeight(70);progress:SetJustifyV("TOP")
 local clock=U.text(panel,"",13,18,-190,234)
 U.text(panel,"Your champion is ready.\nInspect your build while you wait.",12,18,-232,234)
 local readySlots={}
 for i=1,6 do local t=panel:CreateTexture(nil,"ARTWORK");t:SetSize(27,27);t:SetPoint("TOPLEFT",18+(i-1)*38,-143);readySlots[i]=t end
 function ArenaQueueStatus(waiting,needed,size)
  text:Hide();queue:Show();cover:Show();ArenaQueueWaiting=waiting;ArenaQueueNeeded=needed
  back.caption:SetText("Cancel Queue")
  progress:SetText(size.."v"..size.." · Players only\n\n"..waiting.." / "..needed.." players ready")
  for i,t in ipairs(readySlots)do if i<=needed then t:Show();t:SetTexture(i<=waiting and "Interface\\Icons\\Achievement_Arena_2v2_1" or "Interface\\PaperDollInfoFrame\\UI-Backpack-EmptySlot")else t:Hide()end end
 end
 queue:SetScript("OnUpdate",function(_,dt)
  elapsed=elapsed+dt;dots=dots+dt
  clock:SetText(string.format("Time in queue  %02d:%02d",math.floor(elapsed/60),math.floor(elapsed)%60))
  search:SetText("FINDING PLAYERS"..string.rep(".",math.floor(dots)%4))
 end)
end
function ArenaWorldStatus(message,shown)
 ArenaWorldMessage=message
 if shown then text:SetText(message or "");text:Show();queue:Hide();cover:Show()else cover:Hide()end
end
ArenaLobbyViewReady=false
root:RegisterEvent("PLAYER_FARSIGHT_FOCUS_CHANGED");root:SetScript("OnEvent",function()ArenaLobbyViewReady=true end)
