// A viewport-sized lobby and a 1920x1080 arena, with real DPR preserved for input mapping.
window.arenaLobbyResolution=()=>{
 const ratio=innerWidth/innerHeight;
 return ratio>=16/9?[Math.round(1080*ratio),1080]:[1920,Math.round(1920/ratio)];
};
window.arenaDisplayMode='game';
const initial=[1920,1080];
window.arenaDisplayTarget=initial;
const configKey='benilla:/benilla-config/config.toml';
localStorage.setItem(configKey,localStorage.getItem(configKey).replace(/gxResolution = "[^"]+"/,`gxResolution = "${initial[0]}x${initial[1]}"`));
const fitArenaCanvas=()=>{
 const c=document.getElementById('benilla');const dpr=devicePixelRatio||1;
 const [width,height]=window.arenaDisplayTarget;
 const style=document.documentElement.style;
 style.setProperty('--arena-dpr',dpr);style.setProperty('--arena-width',width+'px');style.setProperty('--arena-height',height+'px');
 style.setProperty('--arena-scale',dpr*Math.min(innerWidth/width,innerHeight/height));
};
const watchDpr=()=>matchMedia(`(resolution: ${devicePixelRatio}dppx)`).addEventListener('change',()=>{fitArenaCanvas();watchDpr();},{once:true});
let viewport=innerWidth+'x'+innerHeight;
watchDpr();addEventListener('resize',()=>{fitArenaCanvas();const now=innerWidth+'x'+innerHeight;if(now!==viewport){viewport=now;window.arenaRequestResize?.();}});
addEventListener('DOMContentLoaded',()=>{
 const canvas=document.getElementById('benilla');
 if(canvas)new MutationObserver(fitArenaCanvas).observe(canvas,{attributes:true,attributeFilter:['width','height']});
 fitArenaCanvas();
});
fitArenaCanvas();

window.arenaFitCanvas=fitArenaCanvas;
