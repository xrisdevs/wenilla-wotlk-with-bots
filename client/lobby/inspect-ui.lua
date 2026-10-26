-- Shared native WoW paper doll and read-only talent trees, usable in glue and world VMs.
ArenaUI={}
local U=ArenaUI
function U.text(p,s,size,x,y,w)
 local f=p:CreateFontString(nil,"OVERLAY");f:SetFont("Fonts\\FRIZQT__.TTF",size or 14,"OUTLINE");f:SetPoint("TOPLEFT",p,"TOPLEFT",x,y);f:SetWidth(w or 240);f:SetJustifyH("LEFT");f:SetText(s);return f
end
function U.panel(p,w,h,x,y)
 local f=CreateFrame("Frame",nil,p);f:SetSize(w,h);f:SetPoint("TOPLEFT",p,"TOPLEFT",x,y)
 local bg=f:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints(f);bg:SetTexture(.025,.02,.015,.96)
 f:SetBackdrop({bgFile="Interface\\DialogFrame\\UI-DialogBox-Background",edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border",tile=true,tileSize=32,edgeSize=24,insets={left=6,right=6,top=6,bottom=6}})
 f:SetBackdropColor(.04,.03,.02,.92);return f
end
function U.button(p,s,w,h,x,y,fn)
 local b=CreateFrame("Button",nil,p);b:SetSize(w,h);b:SetPoint("TOPLEFT",p,"TOPLEFT",x,y)
 b:SetNormalTexture("Interface\\Buttons\\UI-Panel-Button-Up");b:SetPushedTexture("Interface\\Buttons\\UI-Panel-Button-Down");b:SetHighlightTexture("Interface\\Buttons\\UI-Panel-Button-Highlight")
 for _,t in ipairs({b:GetNormalTexture(),b:GetPushedTexture(),b:GetHighlightTexture()})do t:SetTexCoord(0,.625,0,.6875)end
 b.caption=U.text(b,s,13,8,-8,w-16);b.caption:SetJustifyH("CENTER");b:SetScript("OnClick",fn);return b
end
function U.inspect(root,getBuild)
 local tip=CreateFrame("GameTooltip","ArenaInspectTooltip",root);tip:SetFrameStrata("TOOLTIP");tip:SetClampedToScreen(true)
 tip:SetBackdrop({bgFile="Interface\\Tooltips\\UI-Tooltip-Background",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=true,tileSize=16,edgeSize=16,insets={left=4,right=4,top=4,bottom=4}});tip:SetBackdropColor(.04,.04,.08,1);tip:Hide()
 local function hover(button,subject,kind)
  local function show()
   local x=button:GetCenter();tip:SetOwner(button,x>GetScreenWidth()/2 and "ANCHOR_LEFT" or "ANCHOR_RIGHT");tip:ClearLines()
   if UnitName and UnitName("player") then
    if kind=="item"then tip:SetInventoryItem("player",subject.inventorySlot)
    elseif kind=="talent"then tip:SetTalent(subject.treeIndex,subject.talentIndex)
    elseif kind=="glyph"then tip:SetGlyph(subject.socket)end
   else
    for _,line in ipairs(subject.tooltip or {})do
     if line[5]~=""then tip:AddDoubleLine(line[1],line[5],line[2],line[3],line[4],line[6],line[7],line[8])
     else tip:AddLine(line[1],line[2],line[3],line[4],true)end
    end
   end
   if tip:NumLines()==0 then tip:AddLine("Loading details...",1,.82,0)end
   tip:Show()
  end
  button:SetScript("OnEnter",show);button:SetScript("OnLeave",function()tip:Hide()end)
  local elapsed=0;button:SetScript("OnUpdate",function(_,dt)
   if tip:IsOwned(button)then elapsed=elapsed+dt;if elapsed>.25 then elapsed=0;show()end end
  end)
 end
 local function icon(p,texture,x,y,size,subject,kind,active)
  local b=CreateFrame("Button",nil,p);b:SetSize(size,size);b:SetPoint("TOPLEFT",p,"TOPLEFT",x,y)
  local t=b:CreateTexture(nil,"ARTWORK");t:SetAllPoints(b);t:SetTexture(texture);t:SetTexCoord(.07,.93,.07,.93);if active==false then t:SetDesaturated(true)end
  local border=b:CreateTexture(nil,"OVERLAY");border:SetTexture("Interface\\Buttons\\UI-Quickslot2");border:SetPoint("CENTER");border:SetSize(size*1.7,size*1.7)
  b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square");hover(b,subject,kind);return b
 end
 local gear=CreateFrame("Frame",nil,root);gear:SetAllPoints(root);gear:SetFrameLevel(25)
 local slots={};local glyphButtons={};local trees={};local nodes={}
 local modal=U.panel(root,math.min(1040,root:GetWidth()-32),660,0,0);modal:ClearAllPoints();modal:SetPoint("CENTER");modal:SetFrameStrata("FULLSCREEN_DIALOG");modal:SetFrameLevel(90);modal:EnableMouse(true);modal:Hide()
 U.text(modal,"TALENTS & GLYPHS",22,22,-19,600):SetTextColor(1,.82,0)
 local pointText=U.text(modal,"",12,22,-49,900)
 U.button(modal,"X",35,28,modal:GetWidth()-55,-15,function()modal:Hide();tip:Hide()end)
 local function line(p,x1,y1,x2,y2,on)
  local t=p:CreateTexture(nil,"BORDER");t:SetTexture(on and .8 or .25,on and .65 or .25,.15,1)
  t:SetSize(math.max(2,math.abs(x2-x1)),math.max(2,math.abs(y2-y1)));t:SetPoint("TOPLEFT",p,"TOPLEFT",math.min(x1,x2),-math.min(y1,y2));return t
 end
 local function refresh()
  tip:Hide();for _,b in ipairs(slots)do b:Hide()end;slots={}
  local b=getBuild();if not b then return end
  local left={3,17,4,11,5,12,9,10};local right={6,7,8,13,14,15,16};local pos={}
  for i,s in ipairs(left)do pos[s]={root:GetWidth()/2-215,-150-(i-1)*48}end
  for i,s in ipairs(right)do pos[s]={root:GetWidth()/2+175,-150-(i-1)*48}end
  pos[0]={root:GetWidth()/2-70,-root:GetHeight()+145};pos[1]={root:GetWidth()/2-20,-root:GetHeight()+145};pos[2]={root:GetWidth()/2+30,-root:GetHeight()+145}
  for _,g in ipairs(b.gear)do
   local xy=pos[g.slot];if xy then
    local node=icon(gear,g.icon,xy[1],xy[2],38,g,"item",true);node.item=g.item;table.insert(slots,node)
   end
  end
  for _,f in ipairs(trees)do f:Hide()end;trees={};nodes={}
  for _,f in ipairs(glyphButtons)do f:Hide()end;glyphButtons={}
  local total=0;local width=(modal:GetWidth()-44)/3
  for i,tree in ipairs(b.talentTrees)do
   total=total+tree.points
   local pane=CreateFrame("Frame",nil,modal);pane:SetSize(width-8,465);pane:SetPoint("TOPLEFT",modal,"TOPLEFT",20+(i-1)*width,-80);table.insert(trees,pane)
   local title=U.text(pane,tree.name.."  "..tree.points,15,8,-4,width-20);title:SetTextColor(1,.82,0)
   local path="Interface\\TalentFrame\\"..tree.background
   for _,q in ipairs({{"-TopLeft",0,30,.8,.6667},{"-TopRight",.8,30,.2,.6667},{"-BottomLeft",0,310,.8,.3333},{"-BottomRight",.8,310,.2,.3333}})do
    local t=pane:CreateTexture(nil,"BACKGROUND");t:SetTexture(path..q[1]);t:SetPoint("TOPLEFT",pane,"TOPLEFT",q[2]*(width-8),-q[3]);t:SetSize(q[4]*(width-8),q[5]*420);t:SetAlpha(.65)
   end
   local byid={};for _,t in ipairs(tree.nodes)do byid[t.id]=t end
   for _,t in ipairs(tree.nodes)do
    if t.prerequisite~=0 and byid[t.prerequisite]then
     local pre=byid[t.prerequisite];local x1=38+pre.column*(width-60)/3;local y1=62+pre.row*37
     local x2=38+t.column*(width-60)/3;local y2=62+t.row*37
     line(pane,x1,y1,x1,y2,t.rank>0);line(pane,x1,y2,x2,y2,t.rank>0)
    end
   end
   for _,t in ipairs(tree.nodes)do
    local n=icon(pane,t.icon,22+t.column*(width-60)/3,-46-t.row*37,31,t,"talent",t.rank>0)
    local r=U.text(n,t.rank.."/"..t.maxRank,10,12,-25,36);r:SetTextColor(t.rank==t.maxRank and 1 or .2,t.rank>0 and 1 or .5,0)
    n.talentId=t.id;n.rank=t.rank;table.insert(nodes,n)
   end
  end
  pointText:SetText(b.name.."  |  "..total.." / 71 points  |  Preset build")
  for i,g in ipairs(b.glyphs)do
   local x=32+(i-1)*(modal:GetWidth()-60)/6
   local n=icon(modal,g.icon,x,-571,34,g,"glyph",true)
   local l=U.text(n,g.minor and "Minor" or "Major",10,-8,-42,65);l:SetJustifyH("CENTER");table.insert(glyphButtons,n)
  end
  ArenaGlyphButtons=glyphButtons;ArenaGearSlots=slots;ArenaTalentNodes=nodes;ArenaTalentTrees=trees;ArenaTalentModal=modal
 end
 refresh()
 return {gear=gear,modal=modal,refresh=refresh,hide=function()gear:Hide();modal:Hide();tip:Hide()end,talents=function()refresh();modal:Show()end}
end
