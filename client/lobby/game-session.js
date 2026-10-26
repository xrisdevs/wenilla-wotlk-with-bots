// The web page only hosts the canvas. All lobby controls and previews live in the game's Lua UI.
export async function connectLobby() {
  if (window.parent === window || !window.parent.__arenaLobby) return;
  async function api(path, body, method = 'POST') {
    const r = await fetch('/api/' + path, {signal:AbortSignal.timeout(20000),method, headers:{'Content-Type':'application/json'}, ...(body == null ? {} : {body:JSON.stringify(body)})});
    const data = await r.json();
    if (!r.ok) throw Error(data.error || 'Could not connect to the arena server.');
    return data;
  }
  for (const id of ['fs','bell']) { const el=document.getElementById(id); if(el)el.style.display='none'; }
  let session = await api('session');
  window.__wenilla_env = {...await api('credentials', null, 'GET'), unattended:'0'};
  localStorage.setItem('benilla:/benilla-config/saved/BotArenaSpectator.lua', 'BotArenaSpectatorDB = { autoSpectate = false, autoUI = false, lobby = true }');
  const {wenilla} = await import('./bridge.js');
  wenilla.on('frame', snapshot=>window.parent.arenaRecovery?.frame(snapshot));
  const [inspectLua, heroLua, worldLua] = await Promise.all(['inspect-ui.lua','hero-lobby.lua','world-lobby.lua'].map(async f => {
    const r=await fetch('/lobby/'+f);if(!r.ok)throw Error('Could not load arena interface.');return r.text();
  }));
  function lua(v) {
    if (v == null) return 'nil';
    if (typeof v === 'string') return JSON.stringify(v);
    if (typeof v === 'boolean' || typeof v === 'number') return String(v);
    if (Array.isArray(v)) return '{'+v.map(lua).join(',')+'}';
    return '{'+Object.entries(v).map(([k,x])=>'['+lua(k)+']='+lua(x)).join(',')+'}';
  }
  const races={1:['HUMAN','Human'],3:['DWARF','Dwarf'],4:['NIGHTELF','NightElf'],11:['DRAENEI','Draenei']};
  function catalog() {
    return {...session, builds:session.builds.map(b=>({...b, raceToken:races[b.raceId][0],scene:races[b.raceId][1],classToken:b.className.replaceAll(' ','').toUpperCase(),previewJson:JSON.stringify(b.previewEquipment)}))};
  }
  let restore=null, resolution=null, resizeRequested=false, displayStarted=0, displayRetried=0;
  window.arenaRequestResize=()=>{resizeRequested=true;};
  async function display(mode) {
    window.arenaDisplayMode=mode;
    const [w,h]=mode==='lobby'?window.arenaLobbyResolution():[1920,1080];
    const target=w+'x'+h;
    window.arenaDisplayTarget=[w,h];window.arenaFitCanvas?.();
    if(resolution!==target){
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      await wenilla.lua(`SetCVar("gxResolution",${lua(target)});RestartGx()`);resolution=target;displayStarted=Date.now();displayRetried=0;return false;
    }
    const c=document.querySelector("canvas");
    if(c?.width===w && c?.height===h)return true;
    if(Date.now()-displayStarted>15000)throw Error('Display resize did not finish. Reload the client to retry.');
    if(Date.now()-displayStarted>750*(displayRetried+1)){await wenilla.lua('RestartGx()');displayRetried++;}
    return false;
  }
  let bootReady=false, busy=false, pending=null, installed=false, worldInstalled=false, game=null, nextPoll=0, returning=false;
  async function worldStatus(message,cover=true) {
    await wenilla.lua(`if ArenaWorldStatus then ArenaWorldStatus(${lua(message)},${cover}) end`);
  }
  async function back() {
    await worldStatus('Returning to character selection...');
    await api('queue',null,'DELETE').catch(()=>{});
    if(pending){
      restore=[session.builds.findIndex(b=>b.id===pending.character.build)+1,pending.mode,pending.size,pending.arena,pending.character.name,pending.character.name];
      const [actualName]=await wenilla.lua('return UnitName and UnitName("player")');
      const leaveName=session.characters.some(c=>c.name===actualName)?actualName:pending.character.name;
      await api('leave',{name:leaveName,logout:true});
    }
    returning=true;
    pending=null;game=null;installed=false;
  }
  setInterval(async()=>{
    if(busy)return;busy=true;
    try {
      const state=wenilla.state?.session?.state;
      if(state==='charselect') {
        if(resizeRequested){
          restore=await wenilla.lua('if ArenaLobbySnapshot then return ArenaLobbySnapshot() end');
          await wenilla.lua('if ArenaLobby then ArenaLobby:Hide() end');installed=false;resizeRequested=false;
        }
        if(!await display('lobby'))return;
        worldInstalled=false;
        if(returning){returning=false;session=await api('session');}
        if(!pending) {
          const [exists]=await wenilla.lua('return ArenaLobby ~= nil');
          if(!installed || !exists) {
            session=await api('session');
            await wenilla.lua(`SetGlueScreen("charcreate"); if CharacterCreate then CharacterCreate:Hide() end; if CharacterSelect then CharacterSelect:Hide() end; if AccountLogin then AccountLogin:Hide() end; ArenaLobbyData=${lua(catalog())};ArenaLobbyRestore=${lua(restore)}`);
            await wenilla.lua(inspectLua);await wenilla.lua(heroLua);installed=true;
            if(!bootReady) {
              await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
              window.__wenilla_progress?.('ready');window.parent.arenaRecovery?.ready();bootReady=true;
            }
          }
          const request=await wenilla.lua('return ArenaLobbyTakeRequest()');
          if(request[0]==='play') {
            const [,id,name,existing,mode,size,arena]=request;
            const build=session.builds.find(b=>b.id===id);
            if(!build)throw Error('Choose a champion.');
            const character=mode==='watch' && session.characters.length ? session.characters[0] : existing ? session.characters.find(c=>c.name===existing) : await api('characters',{build:id,name});
            if(!character)throw Error('Choose one of your saved characters.');
            pending={character,build:session.builds.find(b=>b.id===character.build),mode,size,arena,created:false,entering:false,started:Date.now()};
          }
        }
        if(pending && !pending.entering) {
          const [count]=await wenilla.lua('return GetNumCharacters()');let index=0;
          for(let i=1;i<=count;i++){const [n]=await wenilla.lua(`return GetCharacterInfo(${i})`);if(n===pending.character.name)index=i;}
          if(index) {
            if(!pending.selectionShown){
              await wenilla.lua('ArenaLobbyHide();SetGlueScreen("charselect")');pending.selectionShown=true;return;
            }
            if(pending.selectedIndex!==index){
              await wenilla.lua(`CharacterSelect_SelectCharacter(${index},true)`);pending.selectedIndex=index;return;
            }
            const [selectedName]=await wenilla.lua('return GetCharacterInfo(CharacterSelect.selectedIndex)');
            if(selectedName!==pending.character.name){pending.selectedIndex=null;return;}
            await wenilla.lua('EnterWorld()');pending.entering=true;pending.prepareStarted=Date.now();
          } else if(pending.character.prepared) {
            if(Date.now()-pending.started>45000){pending=null;throw Error('The character list did not refresh. Return to the lobby and retry.');}
            if(!pending.rosterAsked || Date.now()-pending.rosterAsked>2000){await wenilla.lua('GetCharacterListUpdate()');pending.rosterAsked=Date.now();}
          } else if(!pending.created) {
            await wenilla.lua(`CreateCharacter(${lua(pending.character.name)})`);pending.created=true;
          } else if(Date.now()-pending.started>45000){pending=null;throw Error("Character creation did not finish. Return to the lobby and retry.");}

        }
      } else if(state==='inworld' && pending && !returning) {
        if(!worldInstalled) {
          await wenilla.lua(`ArenaActiveBuild=${lua(catalog().builds.find(b=>b.id===pending.character.build))};ArenaActiveMode=${lua(pending.mode)};ArenaActiveName=${lua(pending.character.name)}`);
          await wenilla.lua(inspectLua);await wenilla.lua(worldLua);worldInstalled=true;
          await wenilla.lua('if BotArenaPanel then BotArenaPanel:Hide() end');
        }
        const [action]=await wenilla.lua('local a=ArenaWorldAction;ArenaWorldAction=nil;return a');
        if(action==='back'){await back();return;}
        if(pending.failed)return;
        if(!pending.prepared) {
          const [actualName]=await wenilla.lua('return UnitName("player")');
          if(actualName && actualName!==pending.character.name)throw Error('Entered '+actualName+' instead of '+pending.character.name+'. Return to Lobby and select your character again.');
          await worldStatus('Preparing '+pending.character.name+'...');
          try {await api('prepare',{name:pending.character.name});}
          catch(e){if(/connecting|teleport|combat and/.test(e.message) && Date.now()-(pending.prepareStarted||pending.started)<45000){await worldStatus(e.message);return;}throw e;}
          pending.prepared=true;
          await wenilla.lua(`SlashCmdList.BOTARENA(${lua(pending.mode==='watch'?'show':'hide')})`);
        }
        if(!game)game=await api('play',{name:pending.character.name,mode:pending.mode,size:pending.size,arena:pending.arena});
        if(game.state==='queued') {
          if(!await display('lobby'))return;
          await wenilla.lua(`ArenaQueueStatus(${game.waiting},${game.needed},${pending.size})`);
          if(Date.now()>nextPoll){game=await api('queue',null,'GET');nextPoll=Date.now()+2000;}
        } else if(game.state==='playing') {
          const [arena,view]=await wenilla.lua('return select(2,IsInInstance())=="arena",not not ArenaLobbyViewReady');
          if(arena && (pending.mode!=='watch'||view)) {
            if(!await display('game'))return;
            if(pending.mode==='watch')await wenilla.lua('if UIParent:IsShown() then SlashCmdList.BOTARENA("ui") end');
            await worldStatus('',false);
          } else await worldStatus(pending.mode==='watch'?'Connecting spectator camera...':'Entering the arena...');
        } else if(game.state==='error')await worldStatus(game.message);
      }
    } catch(e) {
      if(/no VM|Lua bridge timed out/.test(e.message))return;
      console.error('Arena lobby:',e.message);
      if(worldInstalled) {
        if(pending)pending.failed=true;
        await worldStatus(e.message+'\n\nUse Return to Lobby to try again.').catch(()=>{});
      }
      else await wenilla.lua(`if ArenaWorldStatus then ArenaWorldStatus(${lua(e.message)},true) elseif ArenaLobbyError then ArenaLobbyError(${lua(e.message)}) end`).catch(()=>{});
    } finally {busy=false;}
  },350);
}
