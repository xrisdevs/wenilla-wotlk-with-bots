// Lives outside the WASM iframe, so a failed client can be discarded and booted cleanly.
(() => {
  let frame, started=Date.now(), lastFrame=0, connectedBefore=false, disconnectedAt=0;
  let recovering=false, attempts=0, stableSince=0;
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  function status(text) {
    let cover=document.getElementById('arena-recovery');
    if(!cover){
      cover=document.createElement('div');cover.id='arena-recovery';cover.setAttribute('role','status');
      Object.assign(cover.style,{position:'fixed',inset:'0',display:'grid',placeItems:'center',background:'#080604',color:'#ffd100',font:'24px Georgia,serif',zIndex:'9999'});
      document.body.append(cover);
    }
    cover.textContent=text;
  }
  async function recover(reason) {
    if(recovering)return;
    recovering=true;attempts++;
    console.warn('Arena client recovery:',reason);
    status('Reconnecting to the arena lobby…');
    frame?.remove(); // Close the crashed client's game sockets before releasing its character.
    await sleep(Math.min(30000,1000*2**Math.min(attempts-1,5)));
    for(;;){
      try{
        const health=await fetch('/healthz',{cache:'no-store',signal:AbortSignal.timeout(10000)});
        if(!health.ok)throw Error('Server restarting');
        const cleanup=await fetch('/api/recover',{method:'POST',signal:AbortSignal.timeout(20000)});
        if(!cleanup.ok && cleanup.status!==401)throw Error('Waiting for character logout');
        break;
      }catch{
        status('Waiting for the server… Returning to the lobby automatically.');
        await sleep(5000);
      }
    }
    started=Date.now();lastFrame=0;connectedBefore=false;disconnectedAt=0;stableSince=0;
    frame=document.createElement('iframe');frame.id='game';frame.title='World of Warcraft Arena';
    frame.allow='fullscreen; autoplay; clipboard-write';
    frame.src='/game/'; // A fresh session has no pending play request: always return to our lobby.
    recovering=false;
    document.body.append(frame);
    status('Loading the arena lobby…');
  }
  window.arenaRecovery={
    attach(child){
      frame=document.getElementById('game');
      const current=()=>frame?.contentWindow===child && !recovering;
      child.addEventListener('error',e=>{if(current() && (e.error || e.message))void recover(e.message || 'Client error');});
      child.addEventListener('unhandledrejection',e=>{if(current())void recover(String(e.reason?.message || e.reason || 'Client error'));});
      const proto=child.GPUAdapter?.prototype;
      if(proto?.requestDevice){
        const requestDevice=proto.requestDevice;
        proto.requestDevice=async function(...args){
          const device=await requestDevice.apply(this,args);
          device.lost.then(info=>{if(current() && info.reason!=='destroyed')void recover('Graphics device lost');});
          return device;
        };
      }
    },
    frame(snapshot){
      if(recovering)return;
      lastFrame=Date.now();
      const session=snapshot.session;
      if(session?.connected){connectedBefore=true;disconnectedAt=0;}
      else if(connectedBefore){disconnectedAt ||= Date.now();}
    },
    ready(){
      document.getElementById('arena-recovery')?.remove();
      stableSince ||= Date.now();
    },
    restart:recover,
  };
  document.addEventListener('visibilitychange',()=>{
    // Hidden tabs can suspend animation entirely; give a resumed tab time to catch up.
    lastFrame=Date.now();disconnectedAt=0;
    if(!stableSince)started=Date.now();
  });
  setInterval(()=>{
    if(recovering || document.hidden)return;
    const now=Date.now();
    if(stableSince && now-stableSince>120000)attempts=0;
    if(disconnectedAt && now-disconnectedAt>10000)void recover('Game connection lost');
    else if(lastFrame && now-lastFrame>45000)void recover('Game stopped responding');
    else if(!stableSince && now-started>300000)void recover('Game startup timed out');
  },2000);
})();
