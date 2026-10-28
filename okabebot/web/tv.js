'use strict';
const token=location.hash.slice(1),canvas=document.querySelector('#room'),ctx=canvas.getContext('2d'),room=new LabRoom.Room();
let state=null,assetStyle='',received=0,motion=null,visible=false,active=true,ready=false,focus='door',hintUntil=0,lastFrame=0,lastIdle=0;
const text=(id,value)=>{const e=document.getElementById(id);if(e.textContent!==value)e.textContent=value;};
async function request(path,data){
  const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-Surface-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store'});
  if(!r.ok)throw Error(r.status===403?'This screen session has ended. Open a new preview or move here again.':'Reconnecting…');
  return r.json();
}
const speaker=typeof BrowserAudio==='function'?new BrowserAudio(request,()=>{}):null;
let soundAttempted=false;
speaker?.setVolume(20);speaker?.poll();
async function enableSound(){
  if(!speaker)return;
  try{await speaker.enable();document.getElementById('enable-sound').hidden=true;}
  catch{document.getElementById('enable-sound').hidden=false;}
}
const soundButton=document.getElementById('enable-sound');if(soundButton)soundButton.onclick=enableSound;
function animatePhase(s){
  if(s.phase==='preview'){visible=true;motion=null;return;}
  if(s.phase==='entering_tv'||s.phase==='leaving_tv'){
    const key=s.transition_id+':'+s.phase;
    if(motion?.key!==key)motion={key,phase:s.phase,id:s.transition_id,start:performance.now(),path:room.actor.transfer(s.phase==='entering_tv'),duration:s.duration_seconds*1000,acknowledged:false,acking:false};
    visible=true;
  }else if(s.phase==='tv'){visible=true;motion=null;}
  else{visible=false;motion=null;}
}
function update(s){
  const set=s.environment?.name||s.lab.title;
  document.title=set;canvas.setAttribute('aria-label',`${s.character.name} in ${set}`);
  text('name',s.lab.title);text('mode',s.phase==='preview'?'PREVIEW':'');
  text('summary',s.morning?`${s.morning.title}. ${s.morning.cards.map(c=>c.title+': '+c.body).join('. ')}`:s.notification?`${s.notification.title}. ${s.notification.body||''}`:`${s.character.name} at ${s.destination_name}.`);
  document.querySelector('#remote-controls').hidden=!s.remote_controls;
  const button=document.querySelector('#return');button.hidden=s.phase==='preview';button.textContent=`→ ${s.return_location.name}`;
  text('connection','');
}
async function poll(){
  if(!active)return;
  try{
    const s=await request('/surfaces/state');
    if(s.environment?.assigned===false)throw Error('Assign a unique scene set to this screen in Locations.');
    if(assetStyle!==s.character.style){ready=false;room.setAssets(await request('/surfaces/assets'),s.character.style);assetStyle=s.character.style;}
    s.receivedAt=performance.now();s.serverOffset=s.server_time*1000-Date.now();state=s;
    room.setDirection?.(s.tv_side);update(s);animatePhase(s);
    speaker?.setVolume(s.audio_volume??20);
    if(s.phase!=='preview'&&!soundAttempted){soundAttempted=true;await enableSound();}
    // Render a real room frame before readiness can hide the other surface.
    room.render(ctx,{state:s,now:performance.now(),visible:false,position:room.actor.position,walking:false,focus});
    received=performance.now();ready=true;
    if(s.phase!=='preview')await request('/surfaces/heartbeat',{});
  }catch(e){visible=false;ready=false;text('connection',e.message);}
  setTimeout(poll,400);
}
function acknowledge(m){
  if(m.acknowledged||m.acking)return;m.acking=true;
  requestAnimationFrame(()=>request('/surfaces/ack',{kind:m.phase==='entering_tv'?'entered':'departed',transition_id:m.id}).then(()=>{m.acknowledged=true;}).catch(()=>{}).finally(()=>{m.acking=false;}));
}
function frame(now){
  requestAnimationFrame(frame);if(now-lastFrame<32)return;lastFrame=now;if(!state)return;
  if(now-received>(state.visibility_lease_seconds*1000-500)){visible=false;ready=false;}
  let position=room.actor.position,walking=false,opacity=1;
  if(motion&&ready){
    const p=Math.min(1,(now-motion.start)/motion.duration);position=LabRoom.pathAt(motion.path,p);walking=p<1;
    opacity=motion.phase==='entering_tv'?Math.min(1,p*6):Math.min(1,(1-p)*6);
    if(p===1){if(motion.phase==='leaving_tv')visible=false;else room.actor.place(position);acknowledge(motion);}
  }else if(visible&&ready&&state.environment?.presentation==='companion'){
    room.actor.place(LabRoom.anchors.center);position=room.actor.position;
  }else if(visible&&ready){
    if(state.notification||state.focus?.active||state.presenter?.activity==='thinking')room.actor.go('bench');
    else if(now-lastIdle>18000){lastIdle=now;const stops=['center','window','rest'];room.actor.go(stops[Math.floor(now/18000)%stops.length]);}
    position=room.actor.update(now);walking=room.actor.walking;
  }
  const localPresenter=speaker?.presenter();
  const rendered=localPresenter?{...state,presenter:localPresenter}:state;
  try{room.render(ctx,{state:rendered,now,visible:visible&&ready,position,walking,focus:now<hintUntil?focus:null,opacity});}
  catch(e){visible=false;ready=false;text('connection','Room renderer unavailable. Returning to the other display.');}
  document.querySelector('#remote-controls').classList.toggle('active',now<hintUntil);
}
async function returnHome(){
  if(!state||state.phase==='preview')return;
  try{await request('/surfaces/return-receiver',{});}catch(e){text('connection',e.message);}
}
const keys={37:'ArrowLeft',38:'ArrowUp',39:'ArrowRight',40:'ArrowDown',13:'Enter',8:'Back',27:'Back',461:'Back'};
function remoteKey(event){
  if(!state?.remote_controls)return;
  let key=({Escape:'Back',Backspace:'Back',GoBack:'Back',' ':'Enter'})[event.key]||event.key;
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter','Back'].includes(key))key=keys[event.keyCode];
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter','Back'].includes(key))return;
  event.preventDefault();if(event.repeat||!ready)return;
  hintUntil=performance.now()+8000;
  const targets=['updates','agenda','door'];
  if(key.startsWith('Arrow'))focus=targets[(targets.indexOf(focus)+(key==='ArrowLeft'||key==='ArrowUp'?-1:1)+targets.length)%targets.length];
  if(state.phase!=='preview')request('/surfaces/input',{key}).catch(()=>{});
  if(key==='Back'||(key==='Enter'&&focus==='door'))returnHome();
}
document.addEventListener('keydown',remoteKey);
document.querySelector('#return').onclick=returnHome;
canvas.addEventListener('click',()=>{if(!state?.remote_controls)return;focus='door';hintUntil=performance.now()+8000;document.querySelector('#return').focus();});
window.addEventListener('pagehide',()=>{
  active=false;speaker?.close();visible=false;ready=false;ctx.clearRect(0,0,canvas.width,canvas.height);
  if(state&&state.phase!=='preview')fetch('/surfaces/closed',{method:'POST',keepalive:true,headers:{'X-Surface-Token':token,'Content-Type':'application/json'},body:JSON.stringify({transition_id:state.transition_id})}).catch(()=>{});
});
window.addEventListener('hashchange',()=>location.reload());
requestAnimationFrame(frame);poll();
