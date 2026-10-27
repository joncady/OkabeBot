/* Paired browser PCM sink. No tool execution or controller credential. */
(function(root){
'use strict';
class BrowserAudio{
 constructor(request,onStatus){this.request=request;this.onStatus=onStatus;this.context=null;this.gain=null;this.cursor=0;this.epoch=null;this.session=crypto.randomUUID().replaceAll('-','');this.stream=null;this.finished=null;this.closed=false;this.volume=.5;}
 async enable(){
  if(!this.context){this.context=new AudioContext();this.context.onstatechange=()=>{if(this.context.state!=='running')this.stop();};this.gain=this.context.createGain();this.gain.gain.value=this.volume;this.gain.connect(this.context.destination);}
  await this.context.resume();
  if(this.context.state!=='running')throw Error('Tap Enable sound to allow playback.');
  const silence=this.context.createBufferSource();silence.buffer=this.context.createBuffer(1,1,24000);silence.connect(this.gain);silence.start();
  await this.tick();
 }
 async restart(){
  // Some output paths survive OS wake as "running" while no longer audible.
  // Rebuild the graph, invalidate old speech and preserve the user's gain.
  const context=this.context;this.suspend();this.context=null;this.gain=null;
  if(context){context.onstatechange=null;await context.close();}
  if(!this.closed)await this.enable();
 }
 suspend(){this.stop();this.session=crypto.randomUUID().replaceAll('-','');this.cursor=0;this.epoch=null;this.finished=null;}
 setVolume(percent){this.volume=Math.max(0,Math.min(100,Number(percent)))/100;if(this.gain)this.gain.gain.value=this.volume;}
 stop(){if(this.stream){this.stream.aborted=true;for(const source of this.stream.sources)try{source.stop();}catch{}this.stream=null;}}
 receive(event){
  if(event.kind==='start'){this.stop();this.stream={id:event.stream_id,next:this.context.currentTime+.15,sources:new Set(),ended:false,aborted:false,envelope:[],start_at:0};}
  const s=this.stream;if(!s||s.id!==event.stream_id)return;
  if(event.kind==='abort'){this.stop();return;}
  if(event.kind==='chunk'){
   const raw=atob(event.pcm_base64),data=new DataView(Uint8Array.from(raw,c=>c.charCodeAt(0)).buffer),count=data.byteLength/2,buffer=this.context.createBuffer(1,count,24000),samples=buffer.getChannelData(0);
   for(let i=0;i<count;i++)samples[i]=data.getInt16(i*2,true)/32768;
   const start=Math.max(s.next,this.context.currentTime+.04);if(!s.start_at)s.start_at=Date.now()/1000+start-this.context.currentTime;
   for(let i=0;i<count;i+=1200){let sum=0,n=Math.min(1200,count-i);for(let j=0;j<n;j++)sum+=samples[i+j]**2;s.envelope.push(Math.min(1,Math.sqrt(sum/n)*6.5));}
   const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.gain);s.sources.add(source);source.onended=()=>{s.sources.delete(source);this.complete(s);};source.start(start);s.next=start+buffer.duration;
  }
  if(event.kind==='end'){s.ended=true;this.complete(s);}
 }
 complete(s){if(s.ended&&!s.sources.size&&!s.aborted){this.finished=s.id;this.onStatus('Playback finished');}}
 presenter(){const s=this.stream;if(!s||s.aborted||!s.start_at||s.ended&&!s.sources.size)return null;return{activity:'speaking',start_at:s.start_at,envelope:s.envelope};}
 async tick(){
  if(!this.context||this.context.state!=='running'||this.closed)return;
  const session=this.session,finished=this.finished,result=await this.request('/surfaces/audio',{session,after:this.cursor,enabled:true,...(finished?{finished}: {})});
  if(this.closed||session!==this.session)return;
  if(this.epoch&&result.epoch!==this.epoch){this.stop();this.cursor=0;}this.epoch=result.epoch;
  if(this.finished===finished)this.finished=null;
  for(const e of result.events||[]){if(e.cursor<=this.cursor)continue;this.receive(e);this.cursor=e.cursor;}
 }
 async poll(){try{await this.tick();}catch(e){this.stop();this.onStatus('Speaker disconnected. Enable sound to reconnect.');}if(!this.closed)setTimeout(()=>this.poll(),150);}
 close(){this.closed=true;this.stop();this.context?.close();}
}
if(typeof module!=='undefined'&&module.exports)module.exports=BrowserAudio;else root.BrowserAudio=BrowserAudio;
})(typeof window==='undefined'?{}:window);
