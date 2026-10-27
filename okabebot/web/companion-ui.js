/* Presentation and explicit capability setup shared by the Mac and phone. */
(function(root){
'use strict';
class CompanionUI {
 static notification(c,n){
  if(!n)return;
  const glyphs={
   github:['01110','11011','11111','01110','01010'],
   calendar:['01010','11111','10001','10101','11111'],
   ring:['00100','01110','01110','11111','00100'],
   spotify:['01110','10001','01110','00100','00000'],
   default:['11111','10001','10101','10001','11111']
  };
  const fit=(text,width)=>{let value=String(text||'').replace(/\s+/g,' ').trim();if(c.measureText(value).width<=width)return value;while(value&&c.measureText(value+'…').width>width)value=value.slice(0,-1);return value+'…';};
  c.save();c.fillStyle='#0b1721';c.fillRect(8,260,304,58);c.strokeStyle='#78b8ad';c.lineWidth=2;c.strokeRect(9,261,302,56);
  c.fillStyle=n.priority==='urgent'?'#f0a07d':'#78b8ad';
  const glyph=glyphs[n.source]||glyphs.default;glyph.forEach((row,y)=>[...row].forEach((v,x)=>{if(v==='1')c.fillRect(17+x*3,273+y*3,3,3);}));
  const count=Array.isArray(n.member_ids)?n.member_ids.length:1;
  c.font='bold 12px monospace';c.fillStyle='#edf1d7';c.fillText(fit(n.title,count>1?218:260),39,278);
  if(count>1){c.font='10px monospace';c.fillStyle='#dbbd73';c.fillText('×'+count,278,278);}
  c.font='11px monospace';c.fillStyle='#b4c6c2';c.fillText(fit(n.body,260),39,296);
  c.restore();
 }
 constructor(speaker){
  this.speaker=speaker;this.error='';this.approved=false;this.sound=false;this.microphone=false;this.skipped=localStorage.getItem('companion-mic-skipped')==='1';this.complete=localStorage.getItem('companion-setup-complete')==='1';this.open=!this.complete;
  window.addEventListener('companion-permissions',event=>{
   if(!window.webkit?.messageHandlers?.companion)return;
   this.microphone=event.detail?.microphone==='granted';this.render();
  });
  this.node=id=>document.querySelector('#'+id);
  this.node('settings').onclick=()=>this.settings(true);
  this.node('settings-close').onclick=()=>this.settings(false);
  this.node('setup-reset').onclick=()=>{this.settings(false);this.open=true;this.render();};
  this.node('setup-enable').onclick=()=>this.enable();
  this.node('setup-skip').onclick=async()=>{this.skipped=true;localStorage.setItem('companion-mic-skipped','1');await this.enable(false);};
  this.node('setup-close').onclick=()=>window.webkit?.messageHandlers?.companion?.postMessage('close');
  this.node('setup-finish').onclick=()=>{if(this.ready()){this.complete=true;this.open=false;localStorage.setItem('companion-setup-complete','1');this.render();}};
  this.render();
 }
 label(node,text){node.setAttribute('aria-label',text);node.setAttribute('title',text);}
 settings(open){this.node('preferences').hidden=!open;this.node('settings').setAttribute('aria-expanded',String(open));this.size();}
 size(){const layout=this.open||!this.node('preferences').hidden?'expanded':'compact';if(layout!==this.layout){this.layout=layout;window.webkit?.messageHandlers?.companion?.postMessage(layout);}}
 ready(){return this.approved&&this.sound&&(this.microphone||this.skipped);}
 render(){
  this.node('setup').hidden=!this.open;this.size();document.body.classList.toggle('setup-open',this.open);
  for(const [id,done,text] of [['pair-step',this.approved,this.approved?'Screen connected':'Approve this screen in dashboard → Locations'],['sound-step',this.sound,this.sound?'Sound ready':'Sound needs a tap'],['mic-step',this.microphone||this.skipped,this.microphone?'Microphone ready':this.skipped?'Microphone off · enable later in settings':navigator.mediaDevices?.getUserMedia?'Microphone needs permission':'Microphone needs trusted HTTPS']]){
   const n=this.node(id);n.textContent=text;n.setAttribute('data-done',String(done));
  }
  this.node('setup-enable').disabled=!this.approved;
  this.node('setup-skip').disabled=!this.approved;
  this.node('setup-finish').disabled=!this.ready();
  this.node('setup-enable').textContent=this.ready()?'Check permissions again':'Enable sound & microphone';
 }
 connected(approved){this.approved=approved;if(!approved)this.open=true;this.render();}
 async enable(wantMicrophone=true){
  this.error='';this.node('setup-error').textContent='';this.node('setup-enable').disabled=true;
  try{
   if(!this.approved)throw Error('Approve this screen in the dashboard first.');
   await this.speaker.enable();this.sound=true;
   if(wantMicrophone){
    if(!navigator.mediaDevices?.getUserMedia)throw Error('Microphone requires trusted HTTPS. You can continue without it.');
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    stream.getTracks().forEach(track=>track.stop()); // Setup never records or submits audio.
    this.microphone=true;this.skipped=false;localStorage.removeItem('companion-mic-skipped');localStorage.setItem('companion-mic-confirmed','1');
   }
  }catch(e){this.node('setup-error').textContent=e.message;this.indicator('error',e.message);}
  this.render();
 }
 async restore(){
  // Stored preferences are hints, never proof of current browser/OS permission.
  if(!this.complete)return;
  try{await this.speaker.enable();this.sound=true;}catch{} // Autoplay may need a fresh gesture.
  if(window.webkit?.messageHandlers?.companion){
   // Read-only OS status. Never open the mic simply to restore the setup UI.
   window.webkit.messageHandlers.companion.postMessage('permissions');this.render();return;
  }
  try{const p=await navigator.permissions.query({name:'microphone'});this.microphone=p.state==='granted';p.onchange=()=>{this.microphone=p.state==='granted';this.render();};}catch{}
  this.render();
 }
 notice(message){
  this.node('notice').textContent=message;this.node('settings-notice').textContent=message;
  this.error=/disconnect|fail|unavailable|denied|permission|reconnect/i.test(message)?message:'';if(this.error)this.indicator('error',message);
 }
 indicator(state,label){
  const icons={ready:'check',moving:'link',thinking:'clock',listening:'mic',speaking:'sound',offline:'link',error:'warn',setup:'settings'};
  const n=this.node('state-icon');n.setAttribute('data-state',state);n.setAttribute('aria-label',label);n.setAttribute('title',label);n.querySelector('use').setAttribute('href','#i-'+(icons[state]||'link'));
 }
 update(state,recording){
  let kind=recording?'listening':state?.presenter?.activity||'ready';
  if(!state)kind='offline';else if(!['tv','idle'].includes(state.phase))kind='moving';else if(state.phase==='idle')kind='ready';
  if(!['listening','speaking','thinking','moving','offline'].includes(kind))kind='ready';
  if(!recording&&this.complete&&!this.ready())kind='setup';
  if(this.error){this.indicator('error',this.error);return;}
  this.indicator(kind,{ready:'Ready',moving:'Moving',thinking:'Thinking',listening:'Listening',speaking:'Speaking',offline:'Reconnecting',setup:'Open settings to enable sound or microphone'}[kind]);
 }
}
if(typeof module!=='undefined'&&module.exports)module.exports=CompanionUI;else root.CompanionUI=CompanionUI;
})(typeof window==='undefined'?{}:window);
