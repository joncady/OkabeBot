/* Pixel-lab scene adapter. No network, credentials, DOM controls or tool calls. */
(function(root){
'use strict';
const W=960,H=600;
const environments=typeof module!=='undefined'&&module.exports?require('./character-environments.js'):root.CharacterEnvironments;
function sampleMotion(data,style,elapsed,activity='idle',blocked=false,stage='',reduced=false,faceSeconds=elapsed){
 const result={clip:'rest',pose:'rest',body_y:0,head_x:0,head_y:0,gaze:0,gaze_y:0,hand:0,foot:0,pose_weight:0};
 const blinkAt=(faceSeconds+style.length*.37)%7.3;result.blink=blinkAt<.14||(Math.floor(faceSeconds/7.3)%3===1&&blinkAt>.32&&blinkAt<.44);
 if(reduced||blocked||activity!=='idle'||!data?.clips)return result;
 elapsed=Math.max(0,elapsed);result.body_y=Math.sin(elapsed*1.15)*.6;
 const owned=data.definitions?.[style]||{},clips=owned.clips||data.clips;
 let clip=(owned.work_stages||data.work_stages)?.[stage],at;
 if(clip)at=elapsed%clips[clip].duration;
 else{const playlist=data.characters?.[style]||[];if(!playlist.length)return result;
  const slot=Math.floor(elapsed/data.idle_cycle_seconds),offset=data.idle_start_seconds+(slot*7+style.length)%5;
  at=elapsed%data.idle_cycle_seconds-offset;clip=playlist[slot%playlist.length];
  if(at<0||at>=clips[clip].duration)return result;
 }
 const definition=clips[clip];const fade=Math.max(0,stage?Math.min(1,elapsed/.5):Math.min(1,at/.5,(definition.duration-at)/.5));result.pose_weight=fade*fade*(3-2*fade);result.clip=clip;result.pose=definition.pose;
 for(const[channel,points]of Object.entries(definition.tracks)){
  let value=points.at(-1)?.[1]||0;
  for(let i=0;i<points.length-1;i++){const[start,a]=points[i],[end,b]=points[i+1];if(at<=end){let t=Math.min(1,Math.max(0,(at-start)/(end-start)));t=t*t*(3-2*t);value=a+(b-a)*t;break;}}
  result[channel]+=value;
 }return result;
}
function noticeKey(value){if(Array.isArray(value))return '['+value.map(noticeKey).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+noticeKey(value[k])).join(',')+'}';return JSON.stringify(value);}
class Notice{
 constructor(){this.last=0;this.current=null;this.desired=null;this.progress=0;this.currentKey=this.desiredKey=noticeKey(null);}
 set(value,now){this.sample(now);this.desiredKey=noticeKey(value);this.desired=JSON.parse(this.desiredKey);
  if(value===null&&this.current!==null){this.current={title:'',body:'',source:''};this.currentKey=noticeKey(this.current);}
  if(this.current===null&&value!==null){this.current=this.desired;this.currentKey=this.desiredKey;this.progress=0;}this.last=now;
 }
 sample(now,reduced=false){const elapsed=Math.max(0,now-this.last);this.last=now;
  if(reduced){this.current=this.desired;this.currentKey=this.desiredKey;this.progress=this.current===null?0:1;}
  else if(this.current!==null){const opening=this.currentKey===this.desiredKey;this.progress=opening?Math.min(1,this.progress+elapsed/.5):Math.max(0,this.progress-elapsed/.3);
   if(!opening&&this.progress===0){this.current=this.desired;this.currentKey=this.desiredKey;}}
  return {notification:this.current,progress:this.progress*this.progress*(3-2*this.progress)};
 }
}
function focusState(s,now,walking=false){
 const f=s?.focus||{},end=f.ends_at;
 const epoch=Number.isFinite(s.server_time)&&Number.isFinite(s.receivedAt)
  ?s.server_time+Math.max(0,now-s.receivedAt)/1000:(Date.now()+(s.serverOffset||0))/1000;
 const seconds=typeof end==='number'&&Number.isFinite(end)?Math.max(0,Math.ceil(end-epoch)):0;
 const active=f.active===true&&seconds>0&&seconds<=10860;
 const quiet=active&&!walking&&(!s.phase||['tv','preview'].includes(s.phase))&&f.ambient_allowed!==false
  &&(!s.presenter?.activity||s.presenter.activity==='idle')&&!s.notification&&!(s.deployments||[]).length;
 return {active,remaining_seconds:active?seconds:0,quiet};
}
function focusBadge(c,s,now,walking=false,origin=[208,8],scale=1){
 const f=focusState(s,now,walking);if(!f.quiet)return false;
 c.save();c.translate(origin[0]-208*scale,origin[1]-8*scale);c.scale(scale,scale);c.imageSmoothingEnabled=false;c.fillStyle='#172b34';c.fillRect(209,8,102,32);c.fillRect(208,10,104,28);
 c.fillStyle='#789b99';c.fillRect(212,8,96,2);c.fillStyle='#42635f';c.fillRect(212,38,96,2);
 c.fillStyle='#9ac5bb';c.fillRect(218,16,12,2);c.fillRect(218,30,12,2);
 for(let i=0;i<5;i++){c.fillRect(220+i*2,18+i*2,2,2);c.fillRect(228-i*2,18+i*2,2,2);}
 c.fillStyle='#c2d9cf';c.font='bold 16px monospace';c.textAlign='left';c.fillText(`${Math.floor(f.remaining_seconds/60)}:${String(f.remaining_seconds%60).padStart(2,'0')}`,238,31);
 c.restore();return true;
}
const anchors={door:[11.45,.25],landing:[11.1,1.9],center:[8,4],bench:[5.8,2.5],window:[2.5,5.5],rest:[8,6.3]};
const edges={door:['landing'],landing:['door','center'],center:['landing','bench','window','rest'],bench:['center'],window:['center'],rest:['center']};
// Center the projected cutaway bounds, including its raised foundation.
const ROOM={width:14,depth:9,height:6.4,foundation:.4,scale:28};
const origin=[W/2-(ROOM.width-ROOM.depth)*ROOM.scale/2,
  H/2-((ROOM.width+ROOM.depth)/2-ROOM.height+ROOM.foundation)*ROOM.scale/2];
const iso=(x,y,z=0)=>[origin[0]+(x-y)*ROOM.scale,origin[1]+(x+y)*ROOM.scale/2-z*ROOM.scale];
const lerp=(a,b,p)=>a.map((v,i)=>v+(b[i]-v)*p);
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function route(from,to){
  const q=[[from]],seen=new Set();
  while(q.length){const path=q.shift(),last=path[path.length-1];if(last===to)return path.map(k=>anchors[k].slice());if(seen.has(last))continue;seen.add(last);for(const n of edges[last])q.push([...path,n]);}
  throw Error('Unreachable room anchor');
}
function pathAt(path,p){
  const lengths=path.slice(1).map((b,i)=>dist(path[i],b)),total=lengths.reduce((a,b)=>a+b,0);let d=Math.max(0,Math.min(1,p))*total;
  for(let i=0;i<lengths.length;i++){if(d<=lengths[i])return lerp(path[i],path[i+1],lengths[i]?d/lengths[i]:1);d-=lengths[i];}return path[path.length-1].slice();
}
// Tiny authored sprite layers; integer pixels, no font glyphs or network assets.
const weatherPixels={
 sun:['...YYY...','..YOOOY..','.YOOOOOY.','YOOOOOOOY','YOOOOOOOY','YOOOOOOOY','.YOOOOOY.','..YOOOY..','...YYY...'],
 cloud:['....SSSS......','..SSWWWWSS....','.SWWWWWWWWSS..','SWWWWWWWWWWWSS','SWWWWWWWWWWWWWS','.SSSSSSSSSSSSS.'],
 moon:['...MMM..','..MM....','.MM.....','MMM.....','MMM.....','.MMM....','..MMMMM.','...MMM..']
};
function weatherSprite(c,condition,x,y,now=0,scale=4){
 const known=['sunny','clear-night','partlycloudy','cloudy','fog','hail','lightning','lightning-rainy','pouring','rainy','snowy','snowy-rainy','windy','windy-variant','exceptional'];
 const kind=known.includes(condition)?condition:'exceptional';
 const colors={Y:'#f3cf69',O:'#eaa54a',S:'#668b9b',W:'#d7e3dc',M:'#d3dbe7'};
 c.save();c.translate(Math.round(x),Math.round(y));c.scale(scale,scale);c.imageSmoothingEnabled=false;
 const pixel=(xx,yy,w,h,color)=>{c.fillStyle=color;c.fillRect(xx,yy,w,h);};
 const layer=(name,xx,yy)=>weatherPixels[name].forEach((row,dy)=>[...row].forEach((v,dx)=>{if(colors[v])pixel(xx+dx,yy+dy,1,1,colors[v]);}));
 const frame=Math.floor(Math.max(0,now)/220)%3;
 if(kind==='sunny'||kind==='partlycloudy'){
  layer('sun',kind==='sunny'?7:1,0);
  for(const [a,b] of [[11,-2],[11,10],[4,4],[18,4]])pixel(a,b,2,1,'#f3cf69');
 }
 if(kind==='clear-night')layer('moon',8,1);
 if(!['sunny','clear-night','exceptional'].includes(kind))layer('cloud',5,5);
 if(['rainy','pouring','lightning-rainy','snowy-rainy'].includes(kind))for(let i=0;i<4;i++)pixel(6+i*4-(frame%2),12+(i+frame)%3,1,kind==='pouring'?3:2,'#74bfdd');
 if(['snowy','snowy-rainy','hail'].includes(kind))for(let i=0;i<3;i++){const xx=7+i*5,yy=12+(i+frame)%3;pixel(xx,yy,1,1,'#e8f3f0');if(kind!=='hail'){pixel(xx-1,yy+1,3,1,'#e8f3f0');pixel(xx,yy+2,1,1,'#e8f3f0');}}
 if(['lightning','lightning-rainy'].includes(kind)){pixel(12,10,3,2,'#f3cf69');pixel(11,12,3,2,'#f3cf69');pixel(13,14,1,2,'#f3cf69');}
 if(['fog','windy','windy-variant'].includes(kind))for(let i=0;i<3;i++)pixel(3+(i%2)*3+(kind==='fog'?0:frame),12+i*2,15-i*2,1,'#a5c5c6');
 if(kind==='exceptional'){pixel(7,2,9,1,'#a5c5c6');pixel(15,3,2,4,'#a5c5c6');pixel(11,7,5,1,'#a5c5c6');pixel(10,8,2,2,'#a5c5c6');pixel(10,12,2,2,'#a5c5c6');}
 c.restore();return kind;
}
class Actor{
  constructor(){this.position=anchors.center.slice();this.path=[];this.target='center';this.last=0;this.walking=false;}
  go(target){if(target===this.target)return;const near=Object.keys(anchors).filter(k=>k!=='door').sort((a,b)=>dist(this.position,anchors[a])-dist(this.position,anchors[b]))[0];this.path=route(near,target);this.target=target;}
  update(now){let budget=Math.min(80,Math.max(0,now-(this.last||now)))*.003;this.last=now;this.walking=!!this.path.length;while(this.path.length&&budget>0){const d=dist(this.position,this.path[0]);if(d<=budget){this.position=this.path.shift().slice();budget-=d;}else{this.position=lerp(this.position,this.path[0],budget/d);budget=0;}}return this.position;}
  transfer(entering){if(entering)return route('door','center');const near=Object.keys(anchors).filter(k=>k!=='door').sort((a,b)=>dist(this.position,anchors[a])-dist(this.position,anchors[b]))[0];return [this.position.slice(),...route(near,'door')];}
  place(position){this.position=position.slice();this.path=[];this.target='center';}
}
function limb(c,start,end,width,color){const dx=end[0]-start[0],dy=end[1]-start[1],length=Math.max(1,Math.hypot(dx,dy)),nx=-dy/length*width,ny=dx/length*width;polygon(c,[[start[0]+nx,start[1]+ny],[start[0]-nx,start[1]-ny],[end[0]-nx,end[1]-ny],[end[0]+nx,end[1]+ny]],color);}
function polygon(c,points,color,outline){c.beginPath();points.forEach((p,i)=>i?c.lineTo(Math.round(p[0]),Math.round(p[1])):c.moveTo(Math.round(p[0]),Math.round(p[1])));c.closePath();c.fillStyle=color;c.fill();if(outline){c.strokeStyle=outline;c.lineWidth=2;c.stroke();}}
function box(c,x,y,z,w,d,h,color){
  polygon(c,[iso(x,y+d,z),iso(x+w,y+d,z),iso(x+w,y+d,z+h),iso(x,y+d,z+h)],color[0],'#101c25');
  polygon(c,[iso(x+w,y,z),iso(x+w,y+d,z),iso(x+w,y+d,z+h),iso(x+w,y,z+h)],color[1],'#101c25');
  polygon(c,[iso(x,y,z+h),iso(x+w,y,z+h),iso(x+w,y+d,z+h),iso(x,y+d,z+h)],color[2],'#101c25');
}
function label(c,text,x,y,size=10,color='#b9d6c4'){c.fillStyle=color;c.font=`${size}px monospace`;c.fillText(String(text),Math.round(x),Math.round(y));}
function lines(c,text,x,y,width,max=2,size=11,color='#d3e4d0'){
  const words=String(text||'').replace(/\s+/g,' ').split(' ');let line='',row=0;
  for(const word of words){const next=(line?line+' ':'')+word;c.font=`${size}px monospace`;if(c.measureText(next).width>width&&line){label(c,line,x,y+row*(size+5),size,color);row++;line=word;if(row>=max)return;}else line=next;}if(row<max)label(c,line,x,y+row*(size+5),size,color);
}
function monitor(c,origin,u,v,draw,focused){
  const [x,y]=origin;c.save();c.transform(u[0]/240,u[1]/240,-v[0]/136,-v[1]/136,x+v[0],y+v[1]);
  c.fillStyle=focused?'#d7bd7a':'#365861';c.fillRect(-7,-7,254,150);c.fillStyle='#091c25';c.fillRect(0,0,240,136);c.fillStyle='#16323a';c.fillRect(4,4,232,2);
  draw(c);c.fillStyle='#92cbaa';c.fillRect(222,127,5,3);c.restore();
}
function primitive(c,frame){for(const [kind,xy,color,width] of frame.slice(1)){c.fillStyle=color;c.strokeStyle=color;c.lineWidth=width||1;c.beginPath();if(kind==='rectangle'){c.fillRect(xy[0],xy[1],xy[2]-xy[0],xy[3]-xy[1]);continue;}if(kind==='ellipse')c.ellipse((xy[0]+xy[2])/2,(xy[1]+xy[3])/2,Math.abs(xy[2]-xy[0])/2,Math.abs(xy[3]-xy[1])/2,0,0,Math.PI*2);else{c.moveTo(xy[0],xy[1]);for(let i=2;i<xy.length;i+=2)c.lineTo(xy[i],xy[i+1]);if(kind!=='line')c.closePath();}if(kind==='line')c.stroke();else c.fill();}}
class Room{
  constructor(){this.notice=new Notice();this.actor=new Actor();this.portraits=[];this.style='';this.background=null;}
  clearPresentation(){this.notice=new Notice();}
  presentation(state,now){
    if(state._notificationPresented)return state;
    const value=state.notification||null,time=now/1000;
    if(noticeKey(value)!==this.notice.desiredKey)this.notice.set(value,time);
    const frame=this.notice.sample(time,state.motion?.reduced_motion===true);
    return {...state,notification:frame.notification,notification_progress:frame.progress,_notificationPresented:true};
  }
  setDirection(direction){
    const left=direction==='right'||direction==='down';if(this.leftDoor===left)return;
    this.leftDoor=left;this.background=null;
    anchors.door=left?[.25,7.6]:[11.45,.25];anchors.landing=left?[1.9,7.1]:[11.1,1.9];
    this.actor.path=[];
  }
  setAssets(assets,style){
    this.motionCatalog=assets.motion_catalog||{};this.avatarSpec=assets.avatar||null;
    if(this.style===style&&this.portraits.length)return;
    this.style=style;this.portraits=assets.frames.map(frame=>{const c=document.createElement('canvas');c.width=480;c.height=320;primitive(c.getContext('2d'),frame);return c;});
  }
  drawStatic(c){
    const cafe=this.scene==='maid-cafe',workshop=this.scene==='pip-workshop',desk=this.scene==='mac-desk',pocket=this.scene==='pocket-nook';
    c.fillStyle='#101b27';c.fillRect(0,0,W,H);
    // Ground and raised cutaway foundation.
    polygon(c,[iso(0,0,-.4),iso(14,0,-.4),iso(14,9,-.4),iso(0,9,-.4)],'#080f1b');
    polygon(c,[iso(0,0),iso(14,0),iso(14,9),iso(0,9)],'#3d555a','#101a25');
    polygon(c,[iso(0,0),iso(14,0),iso(14,0,6.4),iso(0,0,6.4)],pocket?'#776278':cafe?'#8b6660':desk?'#596371':workshop?'#365c60':'#263d4c','#0c1721');
    polygon(c,[iso(0,0),iso(0,9),iso(0,9,6.4),iso(0,0,6.4)],pocket?'#514d68':cafe?'#775452':desk?'#3e4c60':workshop?'#294b50':'#1d303f','#0c1721');
    // Tile grid stays on the floor plane, never on top of furniture.
    for(let x=0;x<14;x++)for(let y=0;y<9;y++){
      polygon(c,[iso(x,y),iso(x+1,y),iso(x+1,y+1),iso(x,y+1)],cafe?((x+y)%2?'#a48c77':'#ddc8ab'):((x+y)%2?'#385156':'#3d575b'),'#31494e');
      if((x*7+y*11)%19===0){const p=iso(x+.2,y+.5);c.fillStyle='#577174';c.fillRect(p[0],p[1],5,2);}
    }
    // Wall skirting and exposed structural edge.
    polygon(c,[iso(0,0,.14),iso(14,0,.14),iso(14,0,.38),iso(0,0,.38)],'#61777d');
    polygon(c,[iso(0,0,.14),iso(0,9,.14),iso(0,9,.38),iso(0,0,.38)],'#4d686f');
    // Soft industrial light strips, on both wall planes.
    for(const [a,b] of [[iso(.4,0,6),iso(13.6,0,6)],[iso(0,.4,6),iso(0,8.6,6)]]){c.strokeStyle='#809e96';c.lineWidth=4;c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();}
    // Left window and night skyline.
    if(!this.leftDoor){
    const a=iso(0,5.4,2),b=iso(0,8.1,2),d=iso(0,5.4,5.5),e=iso(0,8.1,5.5);
    polygon(c,[a,b,e,d],'#0c1d31','#65808b');
    for(let i=0;i<7;i++){const p=iso(0,5.6+i*.35,2.2);c.fillStyle=i%2?'#274358':'#1b3448';c.fillRect(Math.round(p[0]-7),Math.round(p[1]-24-(i%3)*8),10,24+(i%3)*8);}
    c.strokeStyle='#54727d';c.lineWidth=3;c.beginPath();c.moveTo(...iso(0,6.75,2));c.lineTo(...iso(0,6.75,5.5));c.stroke();
    }
  }
  drawArchitecture(c,s,focus,now){
    if(!this.background){this.background=document.createElement('canvas');this.background.width=W;this.background.height=H;this.drawStatic(this.background.getContext('2d'));}
    c.drawImage(this.background,0,0);
    // Notification monitor, mounted on the back wall.
    const n=s.notification,p=s.notification_progress??1,deploy=s.deployments||[];
    monitor(c,iso(1.2,0,1.9),[252,126],[0,-112],m=>{
      m.save();if(n){m.beginPath();m.rect(0,0,240,136);m.clip();m.translate(0,Math.round((1-p)*136));m.globalAlpha*=p;}
      label(m,s.lab?.showcase?'LITTLE LAB':n?(n.source||'UPDATE').toUpperCase():deploy.length?'DEPLOYING':'LAB STATUS',14,24,11,'#78b8ad');
      lines(m,s.lab?.showcase?'VOICE DEMO':n?n.title:deploy.length?'BUILD IN FLIGHT':'ALL SYSTEMS CALM',14,49,210,2,13);
      if(n)lines(m,n.body,14,94,210,2,10,'#86a5a6');else{
        for(let i=0;i<12;i++){m.fillStyle=i<9?'#83b796':'#23454a';m.fillRect(14+i*17,88+Math.round(Math.sin(now/500+i)*6),9,18);}
        if(deploy.length){m.fillStyle='#dbbd73';m.fillRect(14,116,(now/40)%200,3);}
      }
      m.restore();
    },focus==='updates');
    // Small agenda/clock monitor, angled on the other wall.
    monitor(c,iso(0,4.9,2),[112,-56],[0,-104],m=>{
      if(s.lab?.showcase){label(m,'HELLO',18,38,24,'#c9d6ae');label(m,'PIXEL COMPANION',18,85,10,'#8aa8a2');return;}
      const date=new Date(s.server_time*1000+(now-(s.receivedAt||now)));
      label(m,date.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),18,38,24,'#c9d6ae');
      const event=!s.agenda?.stale&&(s.agenda?.events||[])[0];
      if(focusState(s,now).active){const sec=focusState(s,now).remaining_seconds;label(m,`${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`,18,72,19);label(m,'FOCUS',18,100,10,'#8aa8a2');}
      else if(event){label(m,new Date(event.start*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),18,65,11);lines(m,event.title,18,88,204,2,11);}
      else label(m,s.agenda?.stale?'CALENDAR OFFLINE':'NO UPCOMING EVENTS',18,85,10,'#8aa8a2');
    },focus==='agenda');
    // Door is part of the wall plane. The actor crosses its threshold.
    const door=(u,z)=>this.leftDoor?iso(0,8.7-u,z):iso(10.65+u,0,z);
    polygon(c,[door(0,.04),door(2.2,.04),door(2.2,4),door(0,4)],'#0b1721',focus==='door'?'#e3c77d':'#59777b');
    const opening=s.phase==='entering_tv'||s.phase==='leaving_tv';
    if(!opening)polygon(c,[door(.13,.1),door(2.05,.1),door(2.05,3.85),door(.13,3.85)],'#54716c','#203a40');
    else {const hinge=door(.13,.1),top=door(.13,3.85);polygon(c,[hinge,[hinge[0]-35,hinge[1]+18],[top[0]-35,top[1]+18],top],'#54716c','#203a40');}
    const handle=door(1.75,1.7);c.fillStyle='#ccb47a';c.fillRect(handle[0],handle[1],5,4);
    const sign=door(-.35,4.55);c.save();c.translate(...sign);c.transform(1,this.leftDoor?-.5:.5,0,1,0,0);
    c.fillStyle='#172a32';c.fillRect(-3,-22,88,26);c.strokeStyle='#73877b';c.lineWidth=1;c.strokeRect(-3,-22,88,26);
    lines(c,(s.return_location?.name||'').toUpperCase(),2,-12,78,2,7,'#d5c49c');c.restore();
    const title=iso(4.5,0,6.7);c.save();c.translate(...title);c.transform(1,.5,0,1,0,0);label(c,(s.environment?.name||s.lab?.title||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase(),0,0,10,'#a6c7be');c.restore();
  }
  furniture(c){
    if(this.scene==='pocket-nook'){
      box(c,1.6,.5,0,8.8,1.8,1.4,['#79647d','#514d68','#d3b183']);
      box(c,1.6,.5,1.4,8.8,.3,1.1,['#79647d','#514d68','#ab91a1']);
      box(c,10,4,0,1.8,1.1,1.3,['#bc805f','#87573f','#d3b183']);
      const bag=iso(10.9,4.5,1.3);c.strokeStyle='#d3b183';c.lineWidth=4;c.strokeRect(bag[0]-7,bag[1]-10,14,10);
      return;
    }
    if(this.scene==='mac-desk'){
      box(c,1.4,.4,0,9,1.8,1.7,['#765f60','#514b58','#c7a780']);
      box(c,3,.8,1.7,3,.12,1.6,['#293a4e','#192b3d','#7995a5']);
      const display=iso(4.5,.85,2.5);c.fillStyle='#79b8be';c.fillRect(display[0]-24,display[1]-28,48,28);
      c.fillStyle='#d6e8d8';c.fillRect(display[0]-18,display[1]-21,21,3);c.fillRect(display[0]-18,display[1]-13,35,3);
      box(c,4,1.2,1.7,2,.55,.1,['#8d9d9b','#596779','#c1cbc0']);
      const cup=iso(8.7,1.2,1.9);c.fillStyle='#e5d2a5';c.fillRect(cup[0],cup[1]-13,12,13);c.strokeStyle='#e5d2a5';c.strokeRect(cup[0]+11,cup[1]-10,5,7);
      return;
    }
    if(this.scene==='maid-cafe'){
      box(c,1.1,.4,0,10.8,1.5,1.8,['#805947','#654436','#c8a17a']);
      box(c,2.1,.7,1.8,1.5,.8,.9,['#8a9794','#566c70','#bdc9be']);
      for(let i=0;i<3;i++){const p=iso(5+i*1.8,1.1,1.9);c.fillStyle='#f5e2c1';c.fillRect(p[0]-3,p[1]-11,11,10);c.fillStyle='#755147';c.fillRect(p[0]-1,p[1]-11,7,3);}
      for(const x of [2,10.5]){box(c,x,5.6,0,1.3,1.3,1.1,['#80594c','#664337','#d1ad8c']);const p=iso(x+.6,6.1,1.2);c.fillStyle='#dfb9ad';c.fillRect(p[0]-5,p[1]-15,10,15);}
      return;
    }
    // Back-wall workbench, with cabinet bases and a keyboard on its top.
    box(c,1.6,.4,0,1.3,1.25,1.6,['#53635f','#394c4c','#75837b']);
    box(c,7.8,.4,0,1.3,1.25,1.6,['#53635f','#394c4c','#75837b']);
    box(c,1.3,.2,1.6,8.2,1.8,.18,['#7e7665','#525a54','#a5987c']);
    box(c,4.5,.8,1.8,1.6,.55,.1,['#314249','#23343c','#596c6d']);
    for(let i=0;i<4;i++){const p=iso(4.6+i*.3,1,1.94);c.fillStyle='#a3b5ac';c.fillRect(p[0],p[1],3,2);}
    // Coffee cup and glassware; small, deliberate pixel clusters.
    const mug=iso(7.8,1.15,1.85);c.fillStyle='#ddd0ab';c.fillRect(mug[0],mug[1]-12,10,12);c.fillStyle='#584939';c.fillRect(mug[0]+2,mug[1]-12,6,3);
    const flask=iso(2.5,.9,1.9);c.fillStyle='#9cc9c0';c.fillRect(flask[0]+4,flask[1]-20,5,10);c.fillRect(flask[0],flask[1]-10,14,10);c.fillStyle='#78b59b';c.fillRect(flask[0]+2,flask[1]-7,10,6);
  }
  plant(c,x,y){const p=iso(x,y);box(c,x-.3,y-.3,0,.6,.6,.6,['#8e6455','#654c46','#b28a6e']);for(const [dx,dy,w,h] of [[-13,-45,11,24],[1,-54,9,31],[8,-39,14,10],[-20,-30,18,9]]){c.fillStyle=dx<0?'#6b9a81':'#83ad8c';c.fillRect(p[0]+dx,p[1]+dy,w,h);} }
  avatar(c,position,walking,now,s,opacity=1){
    s=this.presentation(s,now);
    if(!this.portraits.length)return;const quiet=focusState(s,now,walking).quiet;
    const live=s.presenter||{},work=s.work||{},age=Number.isFinite(s.receivedAt)?Math.max(0,now-s.receivedAt)/1000:Infinity;
    const stage=age<(work.lease_seconds||0)?work.stage:'';
    const busy=walking||quiet||s.focus?.ambient_allowed===false||Boolean(s.notification)||(s.deployments||[]).length>0||s.media?.is_playing===true||['playing','buffering'].includes(s.media?.player_state);
    const motion=sampleMotion(this.motionCatalog,s.character?.style||'okabe',stage?(work.elapsed_seconds||0)+age:now/1000,live.activity||'idle',busy,stage,s.motion?.enabled===false||s.motion?.reduced_motion===true,now/1000);
    const poseKey=(s.character?.style||'okabe')+':'+motion.pose;
    if(this.poseKey!==poseKey){this.poseKey=poseKey;this.poseStarted=now;}
    if(stage)motion.pose_weight*=Math.min(1,Math.max(0,(now-this.poseStarted)/500));
    const noticeWeight=s._compactNotification&&s.notification?s.notification_progress||0:0;
    if(noticeWeight>0&&(!live.activity||live.activity==='idle')){motion.head_y+=Math.sin(Math.PI*noticeWeight)*2;motion.gaze_y=Math.sin(Math.PI*noticeWeight);}
    const pose=noticeWeight>0?'present':motion.pose,p=iso(...position),step=walking?Math.sin(now/78):0,spec=this.avatarSpec||{body:[],head:{crop:[140,16,200,196],x:-30,y:-91,width:60,height:49},palette:{sleeve:'#d5dbd2',skin:'#dfbca2'}};
    const working=spec.workbench&&['read','write','review','computer'].includes(pose),bob=walking?Math.abs(step)*2:working?0:motion.body_y;

    c.save();c.globalAlpha=opacity;c.fillStyle='#14292c';c.beginPath();c.ellipse(p[0],p[1],19,7,0,0,Math.PI*2);c.fill();c.translate(Math.round(p[0]),Math.round(p[1]-bob));
    for(const part of spec.body){
      if(((working||pose==='present')&&['left_arm','right_arm'].includes(part.part))||(!['rest','tap','scan'].includes(pose)&&part.part==='right_arm'))continue;
      let dy=0;if(part.part==='left_leg'||part.part==='left_arm')dy=Math.round(step*2);
      if(['right_leg','right_arm','right_foot'].includes(part.part))dy=-Math.round(step*2);
      if(part.part==='right_foot')dy-=Math.round(motion.foot);
      c.fillStyle=part.color;
      if(part.kind==='polygon'){polygon(c,part.points.map(([x,y])=>[x,y+dy]),part.color);}
      else{const[x,y,w,h]=part.box;if(part.kind==='ellipse'){c.beginPath();c.ellipse(x+w/2,y+dy+h/2,w/2,h/2,0,0,Math.PI*2);c.fill();}else c.fillRect(x,y+dy,w,h);}
    }
    let mouth=pose==='phone'&&spec.workbench&&Math.sin(now/125)>0?1:0;const elapsed=(Date.now()+(s.serverOffset||0))/1000-live.start_at;
    if(live.activity==='speaking'&&live.envelope){const i=Math.floor(elapsed*20);if(i>=0&&i<live.envelope.length)mouth=Math.min(2,Math.round(live.envelope[i]*2));}
    const blink=(motion.blink??(now%4700>4510))?3:0;c.imageSmoothingEnabled=false;
    // No original resting arms survive the crop.
    const head=spec.head;
    c.drawImage(this.portraits[blink+mouth],...head.crop,head.x+Math.round(motion.head_x),head.y+Math.round(motion.head_y),head.width,head.height);
    if(head.eyes&&!blink&&(motion.clip!=='rest'||pose==='present')){
      c.save();c.translate(head.x+Math.round(motion.head_x),head.y+Math.round(motion.head_y));c.scale(head.width/head.crop[2],head.height/head.crop[3]);
      for(const eye of head.eyes){const[x,y,w,h]=eye.white;c.fillStyle=eye.white_color;c.fillRect(x-head.crop[0],y-head.crop[1],w,h);
        for(const layer of eye.layers){let[px,py,pw,ph]=layer.box;px=Math.max(x,Math.min(x+w-pw,px+Math.round(motion.gaze)*4));py=Math.max(y,Math.min(y+h-ph,py+Math.round(motion.gaze_y)*4));c.fillStyle=layer.color;c.fillRect(px-head.crop[0],py-head.crop[1],pw,ph);}}
      c.restore();
    }
    if(working)this.workbench(c,pose,motion,spec);else this.action(c,pose,motion,spec,now,noticeWeight);
    if(live.activity==='thinking'){c.fillStyle='#d7bd7a';c.fillRect(30,-84,3,3);c.fillRect(35,-91,4,4);}
    c.restore();
  }
  action(c,pose,motion,spec,now,noticeWeight=0){
    if(pose==='present'){
      const p=noticeWeight,scale=.4+.6*p;
      for(const side of [-1,1]){const shoulder=[side*19,-41],elbow=[side*(19+13*p),-29+9*p],hand=[side*120*scale/2.6,(-48+30*p)/2.6];
        limb(c,shoulder,elbow,3.5,spec.palette.sleeve);limb(c,elbow,hand,3,spec.palette.sleeve);c.fillStyle=spec.palette.sleeve;c.fillRect(elbow[0]-4,elbow[1]-4,8,8);
        c.fillStyle=spec.palette.skin;c.fillRect(hand[0]-3,hand[1]-2,6,5);
      }return;
    }
    if(['rest','tap','scan'].includes(pose)){
      if(pose==='scan'&&spec.scan){c.fillStyle='#87c9bd';c.fillRect(-12+Math.round(motion.gaze*7),-66,4,2);}return;
    }
    // Shoulder -> elbow -> hand remains connected, independent of head movement.
    const sleeve=spec.palette.sleeve;
    const handY=Math.round(-23-(['read','write','review'].includes(pose)?22:35)*motion.pose_weight);c.fillStyle=sleeve;c.fillRect(16,-45,7,17);c.fillRect(19,-35,11,7);c.fillRect(25,Math.min(-28,handY+4),6,Math.abs(handY+4+28)+4);
    c.fillStyle=spec.palette.skin;c.fillRect(24,handY,9,9);
    if(pose==='stretch'){c.fillRect(25,-67,6,12);return;}
    if(spec.finger_wag&&pose==='phone'){c.fillRect(27,-70+Math.round(Math.sin(now/130)*2),3,14);return;}
    c.save();c.translate(0,handY+58);c.globalAlpha*=Math.min(1,motion.pose_weight*3);c.fillStyle='#435c60';c.fillRect(23,-67,19,23);
    c.fillStyle=pose==='phone'?'#7daeb6':'#e8dbb2';c.fillRect(25,-65,15,19);
    c.fillStyle='#8e9e87';
    if(pose==='read')c.fillRect(32,-65,1,19);
    else if(pose!=='phone')for(let row=0;row<3;row++)c.fillRect(27,-60+row*5,11,1);
    if(pose==='write'){c.fillStyle='#d4a75d';c.fillRect(37,-62+Math.round(motion.hand),2,12);}c.restore();
  }
  workbench(c,pose,motion,spec){
    const weight=motion.pose_weight,drop=Math.round((1-weight)*20),computer=pose==='computer',stroke=Math.round(motion.hand);
    c.save();c.translate(0,drop);
    polygon(c,[[-35,-18],[35,-18],[44,1],[-44,1]],'#8a6854');c.fillStyle='#4e4141';c.fillRect(-44,1,88,4);
    if(computer){
      c.fillStyle='#c5c6b6';c.fillRect(-17,-15,39,11);
      c.fillStyle='#53656a';for(let row=0;row<2;row++)for(let key=0;key<7;key++)c.fillRect(-13+key*5,-13+row*4,3,2);
    }else{
      polygon(c,[[-13,-17],[15,-17],[21,-3],[-20,-3]],'#4f5350');polygon(c,[[-12,-17],[14,-17],[19,-5],[-18,-5]],'#eee4c5');
      c.fillStyle='#a59678';c.fillRect(-9,-14,18,1);c.fillRect(-11,-10,14,1);c.fillRect(-12,-7,8+stroke,1);
    }c.restore();
    for(const side of [-1,1]){
      const sx=side*19,sy=-41,wx=Math.round(sx+(side*(computer?8:11)-sx)*weight),wy=Math.round(-18+weight*(computer?(side<0?stroke:2-stroke):0)),ex=side*23;
      c.fillStyle=spec.palette.sleeve;c.fillRect(sx-4,sy-2,8,6);limb(c,[sx,sy],[ex,-22],3.5,spec.palette.sleeve);limb(c,[ex,-22],[wx,wy],3,spec.palette.sleeve);c.fillStyle=spec.palette.sleeve;c.fillRect(ex-4,-26,8,8);
      c.fillStyle=spec.palette.skin;c.fillRect(wx-3,wy-2,7,5);
      if(side===1&&pose==='write'){c.strokeStyle='#d8a657';c.lineWidth=2;c.beginPath();c.moveTo(wx+5+stroke,wy-8);c.lineTo(wx-2+stroke,wy+3);c.stroke();c.fillStyle=spec.palette.skin;c.fillRect(wx+1,wy-2,4,3);}
    }
    if(computer){c.save();c.translate(0,drop);c.fillStyle='#a7aca3';c.fillRect(-3,-20,6,9);c.fillStyle='#53656a';c.fillRect(-15,-12,30,3);
      c.fillStyle='#1d303d';c.fillRect(-23,-51,46,31);c.fillStyle='#344f59';c.fillRect(-21,-49,42,26);c.fillStyle='#819996';c.fillRect(-20,-49,40,1);c.fillStyle='#78988f';c.fillRect(-3,-40,6,6);
      c.fillStyle='#1d303d';for(let x=-14;x<=14;x+=7)c.fillRect(x,-28,3,1);c.restore();}
  }
  idleEnvironment(c,now,state,opacity=1){const set=environments.theme(state.character,state.environment);if(state.environment||set==='green-hill')environments.compact(c,now,opacity,set);}
  render(c,model){
    model={...model,state:this.presentation(model.state,model.now)};
    const morning=model.state.morning;
    if(!morning||model.state.environment?.presentation==='companion')return this.renderScene(c,model);
    c.imageSmoothingEnabled=false;c.fillStyle='#101b27';c.fillRect(0,0,W,H);
    c.save();c.beginPath();c.rect(0,0,716,H);c.clip();c.translate(-72,30);c.scale(.9,.9);
    this.renderScene(c,model);c.restore();this.morningCards(c,model,morning);
  }
  morningCards(c,model,morning){
    const cards=Array.isArray(morning.cards)?morning.cards:[];if(!cards.length)return;
    const elapsed=Math.max(0,(model.state.server_time||0)+(model.now-(model.state.receivedAt||model.now))/1000-(morning.prepared_at||0));
    const page=Math.floor(elapsed/Math.max(5,morning.rotation_seconds||12));
    const pages=Math.ceil(cards.length/2),start=(page%pages)*2;
    label(c,'MORNING',740,58,18,'#e3dcb7');
    for(let slot=0;slot<2;slot++){
      const card=cards[start+slot]||(cards.length===1?null:cards[(start+slot)%cards.length]);
      if(!card)continue;
      const y=78+slot*238;
      c.fillStyle='#6e9996';c.fillRect(728,y+7,220,214);c.fillRect(735,y,206,228);
      c.fillStyle='#16323a';c.fillRect(736,y+8,204,212);
      c.fillStyle=card.important?'#e7ad83':'#d7bd7a';c.fillRect(748,y+20,12,12);
      const title=String(card.title).replace(/(\S{15})(?=\S)/g,'$1 ');
      lines(c,title,770,y+32,164,2,17,'#e3dcb7');
      if(card.kind==='weather'&&card.condition&&Number.isFinite(card.temperature_c)){
        weatherSprite(c,card.condition,786,y+58,model.now,4);
        const f=card.temperature_unit==='°F',degrees=Math.round(f?card.temperature_c*9/5+32:card.temperature_c);
        label(c,String(degrees)+(f?'°F':'°C'),748,y+146,26,'#f2db9e');
        lines(c,String(card.condition).replace(/-/g,' ').replace('partlycloudy','partly cloudy'),748,y+172,180,1,17,'#e0eadd');
        const rainy=['rainy','pouring','lightning-rainy'].includes(card.condition),cold=card.temperature_c<=15;
        const gear=[cold?'Jacket':'',rainy?'Umbrella':''].filter(Boolean).join(' + ');
        if(gear)lines(c,gear+' if heading out',748,y+196,180,2,15,'#abc7ba');
        continue;
      }
      const body=String(card.body).replace(/(\S{18})(?=\S)/g,'$1 ');
      lines(c,body,748,y+88,180,card.partial?5:6,18,'#e0eadd');
      if(card.partial)label(c,'Partial source',748,y+211,11,'#a5b6aa');
    }
    for(let i=0;i<pages;i++){c.fillStyle=i===page%pages?'#e0c47d':'#365861';c.fillRect(740+i*16,568,8,5);}
  }

  renderScene(c,model){
    const set=environments.theme(model.state.character,model.state.environment);
    if(this.scene!==set){this.scene=set;this.background=null;}
    if(model.state.environment?.assigned===false){c.clearRect(0,0,W,H);return;}
    if(model.state.environment?.presentation==='companion'){
      c.clearRect(0,0,W,H);c.fillStyle='#101b27';c.fillRect(0,0,W,H);
      c.save();c.translate(W/2-320,H/2-320);c.scale(2,2);this.idleEnvironment(c,model.now,model.state,model.opacity);c.restore();
      if(model.visible){const p=iso(8,4);c.save();c.translate(W/2,H/2+235);c.scale(2.6,2.6);c.translate(-p[0],-p[1]);this.avatar(c,model.position,model.walking,model.now,model.state,model.opacity);c.restore();focusBadge(c,model.state,model.now,model.walking,[728,12],2);}return;
    }
    if(['green-hill','star-light','rooftop-garden'].includes(set)){environments.room(c,model,this,iso,anchors.door,set);if(model.visible)focusBadge(c,model.state,model.now,model.walking,[model.state.morning?460:728,12],2);return;}
    const {state:s,now,visible,position,walking,focus,opacity}=model;
    c.imageSmoothingEnabled=false;this.drawArchitecture(c,s,focus,now);
    // Painter's order follows world depth so the companion can move around props.
    const drawables=[{depth:5,draw:()=>this.furniture(c)},{depth:10.5,draw:()=>this.plant(c,1.3,8)}, {depth:19,draw:()=>box(c,11.2,7,0,1.5,1.2,.55,['#755d55','#584b49','#a38570'])}];
    if(visible)drawables.push({depth:position[0]+position[1],draw:()=>this.avatar(c,position,walking,now,s,opacity)});
    drawables.sort((a,b)=>a.depth-b.depth).forEach(item=>item.draw());
  }
}
const api={Notice,noticeKey,sampleMotion,weatherSprite,Room,Actor,iso,pathAt,route,anchors,W,H,focusState,focusBadge};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabRoom=api;
})(typeof window==='undefined'?{}:window);
