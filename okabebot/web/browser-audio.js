/* Paired PCM sink shared by browser, Mac, TV and native Android. No tool authority. */
(function(root){
'use strict';
function sessionID(){return Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');}
const RATE=24000,MAX_BYTES=RATE*2*30;
class BrowserAudio{
 constructor(request,onStatus,{prebuffer=false,startupBufferMs=240,nativeSink=null,eventTarget=root}={}){
  this.prebuffer=prebuffer;this.startupBufferMs=Math.max(0,Math.min(2000,startupBufferMs));this.request=request;this.onStatus=onStatus;
  this.context=null;this.gain=null;this.cursor=0;this.epoch=null;this.session=sessionID();this.stream=null;this.finished=null;this.closed=false;this.enabled=false;this.volume=.5;
  this.outcomes=new Map();this.waiters=new Map();this.polling=null;
  try{this.native=nativeSink||(root.AmadeusAndroid?.supportsAudioStream?.()?root.AmadeusAndroid:null);}catch{this.native=null;}
  this.eventTarget=eventTarget;this.nativeListener=event=>this.nativeEvent(event.detail);
  if(this.native)this.eventTarget.addEventListener?.('companion-stream',this.nativeListener);
 }
 async enable(){
  if(this.closed)throw Error('Speaker is closed.');
  if(this.native){this.enabled=true;await this.tick();return;}
  if(!this.context){this.context=new AudioContext();this.context.onstatechange=()=>{if(this.context.state!=='running')this.stop('Playback failed: suspended; enable sound to reconnect.');};this.gain=this.context.createGain();this.gain.gain.value=this.volume;this.gain.connect(this.context.destination);}
  await this.context.resume();if(this.context.state!=='running')throw Error('Tap Enable sound to allow playback.');
  this.enabled=true;const silence=this.context.createBufferSource();silence.buffer=this.context.createBuffer(1,1,RATE);silence.connect(this.gain);silence.start();await this.tick();
 }
 async restart(){
  const context=this.context;this.suspend();this.context=null;this.gain=null;
  if(context){context.onstatechange=null;await context.close();}if(!this.closed)await this.enable();
 }
 suspend(){this.enabled=false;this.stop('Playback failed: interrupted; no automatic replay.');this.session=sessionID();this.cursor=0;this.epoch=null;this.finished=null;}
 setVolume(percent){const value=Number(percent);if(!Number.isFinite(value))return;this.volume=Math.max(0,Math.min(100,value))/100;if(this.gain)this.gain.gain.value=this.volume;if(this.native&&this.stream)this.native.streamEvent(JSON.stringify({kind:'volume',stream_id:this.stream.id}),this.volume);}
 async playWav(encoded,levels){
  if(!this.context||this.context.state!=='running'||this.closed)throw Error('Enable sound before playing this reply.');
  const session=this.session,raw=atob(encoded),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));const buffer=await this.context.decodeAudioData(bytes.buffer);
  if(this.closed||session!==this.session)throw Error('Reply audio expired; no automatic replay.');
  this.stop();const s=this.makeStream('local-'+sessionID());s.ended=true;s.envelope=levels||[];this.stream=s;this.schedule(s,buffer);
 }
 makeStream(id){return{id,next:(this.context?.currentTime||0)+.04,sources:new Set(),ended:false,aborted:false,completed:false,envelope:[],pending:[],pendingSamples:0,totalBytes:0,sequence:0,start_at:0,firstAudioTime:null,started:false,prebuffer:this.prebuffer,native:Boolean(this.native),envelopeCarry:[],scheduledSamples:0};}
 remember(id,error=null){
  if(this.outcomes.has(id))return;this.outcomes.set(id,error?{error}:{completed:true});while(this.outcomes.size>8)this.outcomes.delete(this.outcomes.keys().next().value);
  const waiter=this.waiters.get(id);if(waiter){clearTimeout(waiter.timer);this.waiters.delete(id);error?waiter.reject(Error(error)):waiter.resolve();}
 }
 waitForStream(id,timeout=65000){
  if(typeof id!=='string'||!id) return Promise.reject(Error('Missing reply audio stream.'));
  const done=this.outcomes.get(id);if(done)return done.error?Promise.reject(Error(done.error)):Promise.resolve();
  if(this.waiters.has(id))return this.waiters.get(id).promise;
  let resolve,reject;const promise=new Promise((ok,no)=>{resolve=ok;reject=no;});const timer=setTimeout(()=>{if(this.stream?.id===id)this.fail('Reply playback failed: timed out; no automatic replay.');else this.remember(id,'Reply playback failed: timed out; no automatic replay.');},timeout);
  this.waiters.set(id,{promise,resolve,reject,timer});return promise;
 }
 stop(message='Playback failed: interrupted; no automatic replay.'){
  const s=this.stream;if(!s)return;this.stream=null;s.aborted=true;
  if(s.native)try{this.native.stopStream();}catch{}
  for(const source of s.sources)try{source.stop();}catch{}s.pending=[];
  if(!s.completed)this.remember(s.id,message);
 }
 fail(message){if(!/fail|disconnect|expired/i.test(message))message='Playback failed: '+message;const id=this.stream?.id;this.stop(message);if(id)this.remember(id,message);this.enabled=false;try{Promise.resolve(this.request('/surfaces/audio',{session:this.session,after:this.cursor,enabled:false})).catch(()=>{});}catch{}this.onStatus(message);}
 envelope(s,samples){
  for(const sample of samples){s.envelopeCarry.push(sample);if(s.envelopeCarry.length===1200){let sum=0;for(const v of s.envelopeCarry)sum+=v*v;s.envelope.push(Math.min(1,Math.sqrt(sum/1200)*6.5));s.envelopeCarry=[];}}
 }
 receive(event){
  if(this.closed||!this.enabled)return;
  if(!event||typeof event.stream_id!=='string'||!event.stream_id||!['start','chunk','end','abort'].includes(event.kind))throw Error('Invalid audio stream event.');
  if(event.kind==='start'){
   if(event.sample_rate!==undefined&&event.sample_rate!==RATE||event.channels!==undefined&&event.channels!==1||event.encoding!==undefined&&event.encoding!=='pcm_s16le')throw Error('Unsupported audio stream format.');
   if(this.stream?.id===event.stream_id||this.outcomes.has(event.stream_id))return;
   this.stop();const s=this.makeStream(event.stream_id);if(Number.isFinite(event.startup_buffer_ms)){s.startupBufferMs=Math.max(0,Math.min(2000,event.startup_buffer_ms));s.prebuffer=false;}this.stream=s;
   if(s.native)this.native.streamEvent(JSON.stringify(event),this.volume);return;
  }
  const s=this.stream;if(!s||s.id!==event.stream_id||s.aborted||s.completed)return;
  if(event.kind==='abort'){this.fail('Reply playback failed: canceled; no automatic replay.');return;}
  if(event.kind==='chunk'){
   if(s.ended)throw Error('Audio arrived after stream ended.');
   if(event.sequence!==undefined){if(!Number.isInteger(event.sequence)||event.sequence<0)throw Error('Invalid audio chunk order.');if(event.sequence<s.sequence)return;if(event.sequence!==s.sequence)throw Error('Missing audio chunk; no automatic replay.');}
   if(typeof event.pcm_base64!=='string'||event.pcm_base64.length>320000)throw Error('Invalid audio chunk.');
   const raw=atob(event.pcm_base64);if(!raw.length||raw.length%2||raw.length>240000||s.totalBytes+raw.length>MAX_BYTES)throw Error('Invalid or excessive audio.');
   s.totalBytes+=raw.length;s.sequence++;
   const data=new DataView(Uint8Array.from(raw,c=>c.charCodeAt(0)).buffer),samples=new Float32Array(raw.length/2);for(let i=0;i<samples.length;i++)samples[i]=data.getInt16(i*2,true)/32768;this.envelope(s,samples);
   if(s.native)this.native.streamEvent(JSON.stringify(event),this.volume);
   else{const buffer=this.context.createBuffer(1,samples.length,RATE);buffer.getChannelData(0).set(samples);if(s.prebuffer||s.firstAudioTime===null){s.pending.push(buffer);s.pendingSamples+=samples.length;if(!s.prebuffer&&s.pendingSamples>=RATE*(s.startupBufferMs??this.startupBufferMs)/1000)this.flush(s);}else this.schedule(s,buffer);}
  }
  if(event.kind==='end'){
   if(s.ended)return;s.ended=true;
   if(s.envelopeCarry.length){let sum=0;for(const x of s.envelopeCarry)sum+=x*x;s.envelope.push(Math.min(1,Math.sqrt(sum/s.envelopeCarry.length)*6.5));s.envelopeCarry=[];}
   if(!s.totalBytes){this.fail('Voice generation produced no audio.');return;}
   if(s.native)this.native.streamEvent(JSON.stringify(event),this.volume);else{this.flush(s);this.complete(s);}
  }
 }
 flush(s){if(!s.pending.length)return;const joined=this.context.createBuffer(1,s.pendingSamples,RATE),samples=joined.getChannelData(0);let at=0;for(const b of s.pending){samples.set(b.getChannelData(0),at);at+=b.length;}s.pending=[];s.pendingSamples=0;this.schedule(s,joined);}
 schedule(s,buffer){
  const now=this.context.currentTime,start=Math.max(s.next,now+.04);
  if(s.firstAudioTime===null){s.firstAudioTime=start;s.start_at=Date.now()/1000+start-now;}else if(start>s.next+.01){const silent=Math.round((start-s.next)*20);s.envelope.splice(Math.floor(s.scheduledSamples/1200),0,...new Array(Math.min(silent,600)).fill(0));s.scheduledSamples+=silent*1200;}
  const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.gain);s.sources.add(source);source.onended=()=>{s.sources.delete(source);this.complete(s);};source.start(start);s.next=start+buffer.duration;s.scheduledSamples+=buffer.length;
 }
 complete(s){if(s.ended&&!s.sources.size&&!s.aborted&&!s.completed){s.completed=true;this.finished=s.id;this.remember(s.id);this.onStatus('Playback finished');}}
 nativeEvent(event){
  const s=this.stream;if(!s?.native||s.id!==event?.stream_id||s.aborted||s.completed)return;
  if(event.kind==='started'){s.started=true;s.start_at=Date.now()/1000;this.onStatus('Playback started');}
  else if(event.kind==='completed'){if(!s.ended){this.fail('Phone audio ended before its stream finished.');return;}this.complete(s);}
  else if(event.kind==='failed')this.fail('Phone playback failed or was interrupted; no automatic replay.');
 }
 buffering(){const s=this.stream;return Boolean(s&&!s.aborted&&!s.completed&&!this.presenter());}
 presenter(){
  const s=this.stream;if(!s||s.aborted||s.completed)return null;
  if(s.native){if(!s.started)return null;return{activity:'speaking',start_at:s.start_at,envelope:s.envelope};}
  if(s.firstAudioTime===null||!s.sources.size||this.context.currentTime<s.firstAudioTime)return null;
  if(!s.started){s.started=true;this.onStatus('Playback started');}
  return{activity:'speaking',start_at:Date.now()/1000-(this.context.currentTime-s.firstAudioTime),envelope:s.envelope};
 }
 async tick(){
  if(this.closed||!this.enabled||!this.native&&(!this.context||this.context.state!=='running'))return;
  if(this.polling)return this.polling;
  const session=this.session,finished=this.finished;
  const operation=(async()=>{const result=await this.request('/surfaces/audio',{session,after:this.cursor,enabled:true,...(finished?{finished}:{})});if(this.closed||session!==this.session)return;
   if(this.epoch&&result.epoch!==this.epoch){if(!this.stream?.id.startsWith('local-'))this.stop('Playback failed: audio service restarted; no automatic replay.');this.cursor=0;}this.epoch=result.epoch;
   if(this.finished===finished)this.finished=null;
   for(const event of result.events||[]){if(!Number.isInteger(event.cursor)||event.cursor<=this.cursor)continue;try{this.receive(event);}catch(error){this.cursor=event.cursor;this.fail(error.message);throw error;}this.cursor=event.cursor;}
  })();this.polling=operation;try{await operation;}finally{if(this.polling===operation)this.polling=null;}
 }
 async poll(){try{await this.tick();}catch(error){if(!this.stream?.id.startsWith('local-')&&this.enabled)this.fail('Speaker disconnected. Enable sound to reconnect.');else this.onStatus('Speaker disconnected. Enable sound to reconnect.');}if(!this.closed)setTimeout(()=>this.poll(),150);}
 close(){this.closed=true;this.enabled=false;this.stop('Playback failed: speaker closed; no automatic replay.');for(const id of this.waiters.keys())this.remember(id,'Playback failed: speaker closed; no automatic replay.');this.eventTarget.removeEventListener?.('companion-stream',this.nativeListener);this.context?.close();}
}
if(typeof module!=='undefined'&&module.exports)module.exports=BrowserAudio;else root.BrowserAudio=BrowserAudio;
})(typeof window==='undefined'?{}:window);
