'use strict';
const canvas=document.querySelector('#character'),ctx=canvas.getContext('2d'),room=new LabRoom.Room();
const native=location.search.includes('native=1');document.body.classList.toggle('native',native);
const android=location.search.includes('android=1')&&Boolean(window.AmadeusAndroid);document.body.classList.toggle('android',android);
let secret=android?window.AmadeusAndroid.deviceToken():localStorage.getItem('companion-device');
if(!secret){secret=Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');localStorage.setItem('companion-device',secret);}
let name=localStorage.getItem('companion-name')||(android?'Android companion':native?'Mac companion':'Phone companion'),state=null,registered=false,style='',lastSeen=0,motion=null,visible=false,stopped=false,pollTimer=null,pollGeneration=0;
let displayApproved=false,mobileWorking=false,nativeVoice=null;
const summon=document.querySelector('#summon');
const status=document.querySelector('#status'),notice=document.querySelector('#notice'),mic=document.querySelector('#mic');
document.querySelector('#screen-name').value=name;
function setStatus(message){if(status.textContent!==message)status.textContent=message;}
async function request(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-Surface-Token':secret,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,cache:'no-store'});const value=await r.json();if(!r.ok)throw Error(value.error||'Screen unavailable. Check pairing and the current turn.');return value;}
function presentation(s){const speaking=nativeVoice||speaker.presenter();return speaking?{...s,presenter:speaking}:(mobileWorking||speaker.buffering?.())?{...s,presenter:{activity:'thinking'}}:s;}
let ui;const speaker=new BrowserAudio(request,message=>{if(ui){ui.sound=speaker.enabled;ui.notice(message,'audio');ui.render();}});ui=new CompanionUI(speaker);speaker.poll();
const label=(node,text)=>ui.label(node,text);
document.querySelector('#native-close').onclick=()=>window.webkit?.messageHandlers?.companion?.postMessage('close');
document.querySelector('#speaker-enable').onclick=async()=>{try{await speaker.restart();ui.sound=true;ui.clearError('audio');ui.render();ui.notice('Sound enabled on this device (or its linked speaker).','audio');}catch(e){ui.notice(e.message,'audio',true);}};
document.querySelector('#speaker-volume').value=localStorage.getItem('companion-speaker-volume')??50;speaker.setVolume(document.querySelector('#speaker-volume').value);
document.querySelector('#speaker-volume').oninput=e=>{speaker.setVolume(e.target.value);localStorage.setItem('companion-speaker-volume',e.target.value);};
let tapMode=localStorage.getItem('companion-tap-mode')==='1'||(android&&localStorage.getItem('companion-tap-mode')===null);
function micLabel(){const text=(mobileWorking||speaker.buffering?.())?'Thinking…':capture?(capture.node?'Tap to send':'Starting mic…'):tapMode?'Tap to talk':'Hold to talk';label(mic,text);if(android)mic.dataset.label=text;document.querySelector('#mic-mode').textContent=tapMode?'Use hold mode':'Use tap mode';}
document.querySelector('#mic-mode').onclick=()=>{if(capture)stopRecording(true);tapMode=!tapMode;localStorage.setItem('companion-tap-mode',String(Number(tapMode)));micLabel();};
summon.onclick=async()=>{
 summon.disabled=true;
 try{await request('/surfaces/summon',{});ui.clearError('action');setStatus('Calling companion here…');}
 catch(e){ui.notice(e.message,'action',true);summon.disabled=!registered;}
};
async function poll(generation=pollGeneration){if(stopped||generation!==pollGeneration)return;try{
 if(!registered){const p=await request('/surfaces/register',{name,kind:android?'android':native?'mac':'browser'});if(stopped||generation!==pollGeneration)return;document.querySelector('#device-name').textContent=p.name;displayApproved=Boolean(p.approved);ui.connected(p.approved);if(!p.approved){summon.disabled=true;setStatus('Approve this screen in the dashboard → Locations.');return;}registered=true;ui.restore();}
 const s=await request('/surfaces/state');if(stopped||generation!==pollGeneration)return;if(s.environment?.assigned===false)throw Error('Assign a unique scene set to this screen in Locations.');if(style!==s.character.style){room.setAssets(await request('/surfaces/assets'),s.character.style);style=s.character.style;}
 if(stopped||generation!==pollGeneration)return;
 ui.clearError('connection');s.receivedAt=performance.now();s.serverOffset=s.server_time*1000-Date.now();state=s;if(android)window.AmadeusAndroid.receiverLease?.(s.phase==='tv'?s.transition_id:'');lastSeen=performance.now();const owned=['preparing','leaving_pi','entering_tv','tv','leaving_tv'].includes(s.phase);
 // Readiness follows an actual successful frame, never only a network response.
 draw(performance.now());if(owned)await request('/surfaces/heartbeat',{});
 if(!capture)setStatus((nativeVoice||speaker.presenter())?'Speaking…':(mobileWorking||speaker.buffering?.())?'Thinking…':s.phase==='tv'?(android?(tapMode?'Tap once to talk · tap again to send':'Hold to talk · release to send'):'Here with you'):owned?'Moving…':'Call companion here to talk');
 summon.disabled=owned;label(summon,s.phase==='tv'?'Companion is here':owned?'Companion is coming…':'Call companion here');ui.update(presentation(s),Boolean(capture?.node));
 document.querySelector('#return').disabled=!owned;mic.disabled=mobileWorking||s.phase!=='tv'||!navigator.mediaDevices?.getUserMedia;
 if(!navigator.mediaDevices?.getUserMedia)ui.notice('Phone microphone needs trusted HTTPS. The Mac app uses localhost.','capability');
 }catch(e){if(stopped||generation!==pollGeneration)return;summon.disabled=true;state=null;visible=false;registered=false;setStatus(e.message);ui.notice(e.message,'connection',true);ui.update(null,false);}finally{if(!stopped&&generation===pollGeneration)pollTimer=setTimeout(()=>poll(generation),1000);}}
function draw(now){ctx.clearRect(0,0,320,320);if(!native){ctx.fillStyle='#101b27';ctx.fillRect(0,0,320,320);}if(!state||now-lastSeen>5000||!room.portraits.length)return;
 const phase=state.phase,key=state.transition_id+phase;let x=0,y=0,opacity=1,walking=false;
 visible=phase==='tv'||phase==='entering_tv'||phase==='leaving_tv';
 if(phase==='entering_tv'||phase==='leaving_tv'){
  if(motion?.key!==key)motion={key,start:now,acked:false};const p=Math.min(1,(now-motion.start)/(state.duration_seconds*1000)),side=state.tv_side||'left';
  const amount=(phase==='entering_tv'?1-p:p)*360,sign=side==='left'?1:-1;
  if(side==='up'||side==='down')y=amount*(side==='up'?1:-1);else x=amount*sign;
  walking=p<1;opacity=phase==='entering_tv'?Math.min(1,p*6):Math.min(1,(1-p)*6);
  if(p===1&&!motion.acked){motion.acked=true;request('/surfaces/ack',{kind:phase==='entering_tv'?'entered':'departed',transition_id:state.transition_id}).catch(()=>{motion.acked=false;});}
 }else motion=null;
 if(visible){const presented={...state,presenter:capture?.node?{activity:'listening'}:nativeVoice||speaker.presenter()||((mobileWorking||speaker.buffering?.())?{activity:'thinking'}:null)||state.presenter};if(state.environment?.presentation==='room'){
  ctx.save();ctx.translate(0,60);ctx.scale(1/3,1/3);room.render(ctx,{state:presented,now,visible:true,position:[8+x*3/56+y*3/28,4-x*3/56+y*3/28],walking,opacity,focus:null});ctx.restore();
 }else{room.idleEnvironment?.(ctx,now,state,opacity);const p=LabRoom.iso(8,4);ctx.save();ctx.translate(160+x,278+y);ctx.scale(2.6,2.6);ctx.translate(-p[0],-p[1]);room.avatar(ctx,[8,4],walking,now,presented,opacity);ctx.restore();LabRoom.focusBadge?.(ctx,presented,now,walking);}}
 if(visible)CompanionUI.notification(ctx,state.notification);
}
function frame(now){try{draw(now);}catch(e){state=null;visible=false;setStatus('Character renderer reconnecting…');}finally{requestAnimationFrame(frame);}}requestAnimationFrame(frame);
document.querySelector('#name-form').onsubmit=e=>{e.preventDefault();name=document.querySelector('#screen-name').value.trim();localStorage.setItem('companion-name',name);registered=false;notice.textContent='Rename approved screens from the dashboard.';};
document.querySelector('#return').onclick=()=>request('/surfaces/return-receiver',{}).then(()=>ui.clearError('action')).catch(e=>ui.notice(e.message,'action',true));
const video=document.querySelector('#video');document.querySelector('#pip').onclick=async()=>{if(android){window.AmadeusAndroid.pictureInPicture();return;}try{if(!canvas.captureStream||!video.requestPictureInPicture)throw Error('Video PiP is not available in this browser.');video.srcObject=canvas.captureStream(24);await video.play();await video.requestPictureInPicture();ui.notice('PiP is view-only. Return to this page to use the mic.','pip');}catch(e){video.srcObject?.getTracks().forEach(t=>t.stop());video.srcObject=null;ui.notice(e.message,'pip',true);}};
video.addEventListener('leavepictureinpicture',()=>{video.srcObject?.getTracks().forEach(t=>t.stop());video.srcObject=null;});
// Capture only during an explicit hold. Resample mono PCM to the existing 16 kHz WAV path.
let capture=null;micLabel();
async function startRecording(e){e.preventDefault();if(capture||mic.disabled||mobileWorking)return;const session={released:false};capture=session;micLabel();setStatus('Starting microphone…');try{
 await speaker.enable();
 session.stream=await navigator.mediaDevices.getUserMedia({audio:true});if(session.released){session.stream.getTracks().forEach(t=>t.stop());return;}
 session.audio=new AudioContext();await session.audio.resume();session.parts=[];session.count=0;session.source=session.audio.createMediaStreamSource(session.stream);session.node=session.audio.createScriptProcessor(4096,1,1);
 session.node.onaudioprocess=event=>{if(session.count<session.audio.sampleRate*20){const samples=event.inputBuffer.getChannelData(0).slice();session.parts.push(samples);session.count+=samples.length;}};
 session.source.connect(session.node);session.node.connect(session.audio.destination);ui.microphone=true;ui.sound=true;ui.clearError('capture');ui.clearError('setup');ui.clearError('voice');ui.clearError('audio');ui.render();micLabel();ui.update(state,true);mic.setAttribute('aria-pressed','true');setStatus(tapMode?'Listening… tap to send':'Listening… release to send');session.timer=setTimeout(stopRecording,20000);
 }catch(e){if(capture===session)await stopRecording(true);else session.stream?.getTracks().forEach(t=>t.stop());ui.notice(e.message,'capture',true);}}
async function stopRecording(cancel=false){const s=capture;if(!s)return;s.released=true;capture=null;clearTimeout(s.timer);mic.setAttribute('aria-pressed','false');micLabel();ui.update(state,false);if(!s.audio){s.stream?.getTracks().forEach(t=>t.stop());return;}
 s.node?.disconnect();s.source?.disconnect();s.stream.getTracks().forEach(t=>t.stop());const rate=s.audio.sampleRate;await s.audio.close();if(!s.count||cancel===true)return;
 if(android){mobileWorking=true;mic.disabled=true;micLabel();}
 try{await speaker.restart();}catch(e){mobileWorking=false;ui.sound=false;ui.render();ui.notice('Enable sound before sending this recording.','audio',true);return;}
 const samples=new Float32Array(s.count);let offset=0;for(const part of s.parts){samples.set(part,offset);offset+=part.length;}
 const length=Math.floor(samples.length*16000/rate),raw=new ArrayBuffer(44+length*2),v=new DataView(raw),put=(at,text)=>{for(let i=0;i<text.length;i++)v.setUint8(at+i,text.charCodeAt(i));};
 put(0,'RIFF');v.setUint32(4,36+length*2,true);put(8,'WAVE');put(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);put(36,'data');v.setUint32(40,length*2,true);
 for(let i=0;i<length;i++){const sample=Math.max(-1,Math.min(1,samples[Math.floor(i*rate/16000)]));v.setInt16(44+i*2,sample*32767,true);}
 let binary='';for(const b of new Uint8Array(raw))binary+=String.fromCharCode(b);
 try{mobileWorking=android;ui.update(presentation(state),false);setStatus('Thinking…');const reply=await request(android?'/mobile/voice':'/surfaces/voice',{clip_id:'screen-'+crypto.randomUUID(),wav_base64:btoa(binary),...(android&&window.AmadeusAndroid.supportsAudioStream?.()?{playback_mode:'stream'}:{})});if(android&&reply.playback_mode==='stream'){if(state?.phase!=='tv')throw Error('Companion moved; reply audio was not replayed.');await speaker.waitForStream(reply.stream_id);}else if(android&&reply.wav_base64){if(state?.phase!=='tv')throw Error('Companion moved; reply audio was not replayed.');if(window.AmadeusAndroid.playReply)await playNativeReply(reply);else await speaker.playWav(reply.wav_base64,reply.levels);}ui.clearError('voice');ui.clearError('audio');setStatus(android?'Ready':'Sent · thinking…');}catch(e){ui.notice(e.message,/playback|speaker|audio|sound/i.test(e.message)?'audio':'voice',true);}finally{mobileWorking=false;mic.disabled=state?.phase!=='tv';micLabel();ui.update(presentation(state),false);}
}
function playNativeReply(reply){
 return new Promise((resolve,reject)=>{
  const timeout=setTimeout(()=>finish('failed'),Math.max(45000,(reply.seconds+15)*1000));
  function finish(result){if(result==='started'){nativeVoice={activity:'speaking',start_at:Date.now()/1000,envelope:reply.levels};setStatus('Speaking…');return;}clearTimeout(timeout);window.removeEventListener('companion-audio',listener);nativeVoice=null;if(result==='completed')resolve();else reject(Error('Phone playback failed or was interrupted. Please check phone media volume.'));}
  const listener=event=>finish(event.detail);window.addEventListener('companion-audio',listener);
  window.AmadeusAndroid.playReply(reply.wav_base64,speaker.volume);
 });
}
mic.oncontextmenu=e=>e.preventDefault();mic.onselectstart=e=>e.preventDefault();
mic.onpointerdown=e=>{e.preventDefault();if(tapMode)return;mic.setPointerCapture(e.pointerId);startRecording(e);};
function toggleRecording(e){if(capture)stopRecording();else{label(mic,'Tap to send');startRecording(e);}}
mic.onpointerup=e=>{if(!tapMode){e.preventDefault();stopRecording();}};
mic.onpointercancel=()=>{if(!tapMode)stopRecording(true);};
mic.onclick=e=>{e.preventDefault();if(tapMode&&!mic.disabled){if(capture&&!capture.node)return;toggleRecording(e);}};
mic.onkeydown=e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat&&!tapMode)startRecording(e);};mic.onkeyup=e=>{if((e.key===' '||e.key==='Enter')&&!tapMode)stopRecording();};
window.addEventListener('blur',()=>stopRecording(true));
window.addEventListener('companion-sleep',()=>{stopRecording(true);speaker.suspend();});
window.addEventListener('pagehide',event=>{stopped=true;pollGeneration++;clearTimeout(pollTimer);stopRecording(true);if(event.persisted)speaker.suspend();else speaker.close();if(state&&['tv','entering_tv','leaving_tv'].includes(state.phase))fetch('/surfaces/closed',{method:'POST',keepalive:true,headers:{'X-Surface-Token':secret,'Content-Type':'application/json'},body:JSON.stringify({transition_id:state.transition_id})}).catch(()=>{});});

async function recoverAudio(){
 await stopRecording(true);if(!ui.complete)return;
 try{await speaker.restart();ui.sound=true;ui.clearError('audio');ui.render();}catch(e){ui.sound=false;ui.render();ui.notice('Tap Enable sound to restore the speaker.','audio',true);}
}
window.addEventListener('companion-wake',()=>recoverAudio());
window.addEventListener('companion-audio-poll',()=>speaker.tick().catch(()=>ui.notice('Speaker disconnected. Enable sound to reconnect.','audio')));
window.addEventListener('companion-display',event=>{if(!native||!displayApproved)return;request('/surfaces/display-signal',event.detail).catch(()=>{});});
window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;registered=false;lastSeen=0;state=null;poll();recoverAudio();}});
// Connectivity alone does not prove recovery; successful scoped operations clear errors.
poll();
