const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {Actor,pathAt,route,anchors,iso}=require('../okabebot/web/lab-room.js');
test('room paths use connected floor anchors and preserve doorway direction',()=>{
 const path=route('door','bench');assert.deepEqual(path[0],anchors.door);assert.deepEqual(path.at(-1),anchors.bench);assert.deepEqual(pathAt(path,0),anchors.door);assert.deepEqual(pathAt(path,1),anchors.bench);
 for(let i=0;i<=100;i++){const [x,y]=pathAt(path,i/100);assert.ok(x>=0&&x<=14&&y>=0&&y<=9);}
 assert.ok(iso(...anchors.door)[0]>iso(...anchors.center)[0]);
});
test('interrupted idle walk exits continuously without teleporting',()=>{
 const actor=new Actor();actor.go('window');actor.update(100);actor.update(150);const position=actor.position.slice(),exit=actor.transfer(false);
 assert.deepEqual(exit[0],position);assert.deepEqual(exit.at(-1),anchors.door);assert.ok(actor.walking);
});
async function browser(phase='tv',broken=false,audio=false,audioState={}){
 const calls=[],events={},nodes={},renders=[];let raf;
 function node(id){return nodes[id]||=( {textContent:'',classList:{toggle(){}},setAttribute(){},addEventListener(){},focus(){},getContext(){return {clearRect(){}};}} );}
 const state={phase,remote_controls:true,transition_id:'transfer',duration_seconds:2,visibility_lease_seconds:6,character:{style:'okabe',name:'Companion'},lab:{title:'Custom room'},return_location:{name:'Desk nook'},destination_name:'Den screen',server_time:1000,presenter:{activity:'speaking',start_at:1}};
 const audioCalls=[];
 const context={...(audio?{BrowserAudio:class{setVolume(v){audioCalls.push(['volume',v]);}poll(){}async enable(){audioCalls.push(['enable']);if(audio==='blocked')await new Promise(()=>{});}close(){audioCalls.push(['close']);}presenter(){return audioState.presenter||null;}buffering(){return Boolean(audioState.buffering);}}}:{}),console,LabRoom:{Room:class{constructor(){this.actor={position:[8,4],transfer(){return [[1,1],[2,2]];},go(){},update(){return [8,4];}};}setAssets(){}render(ctx,value){renders.push(value);if(broken)throw Error("Broken renderer");}}},location:{hash:'#scoped',reload(){}},performance:{now:()=>100},Date,requestAnimationFrame(fn){raf=fn;},setTimeout(){},document:{getElementById:id=>node("#"+id),querySelector:selector=>node(selector),addEventListener:(event,fn)=>events[event]=fn},window:{addEventListener:(event,fn)=>events[event]=fn},fetch:async(path,options)=>{calls.push({path,data:options.body&&JSON.parse(options.body)});return{ok:true,json:async()=>path==='/surfaces/state'?state:{frames:[[]]}};}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/tv.js','utf8'),context);await new Promise(setImmediate);return{calls,events,nodes,audioCalls,renders,frame:now=>raf(now)};
}
test('remote Enter keyCode and Back each request exactly one return',async()=>{
 const b=await browser();b.events.keydown({key:'Unidentified',keyCode:13,preventDefault(){},repeat:false});await new Promise(setImmediate);
 assert.equal(b.calls.filter(c=>c.path==='/surfaces/return-receiver').length,1);
 assert.deepEqual(b.calls.find(c=>c.path==='/surfaces/input').data,{key:'Enter'});
 b.events.keydown({key:'Enter',preventDefault(){},repeat:true});assert.equal(b.calls.filter(c=>c.path==='/surfaces/return-receiver').length,1);
 b.events.keydown({key:'Escape',preventDefault(){}});await new Promise(setImmediate);assert.equal(b.calls.filter(c=>c.path==='/surfaces/return-receiver').length,2);
});
test('preview remote is read-only and exposes the configured destination label',async()=>{
 const b=await browser('preview');b.events.keydown({key:'Enter',preventDefault(){}});await new Promise(setImmediate);
 assert.equal(b.calls.filter(c=>c.data).length,0);assert.equal(b.nodes['#return'].textContent,'→ Desk nook');
});

test('renderer failure never sends ready or enables remote movement',async()=>{
 const b=await browser('tv',true);b.events.keydown({key:'Enter',preventDefault(){}});await new Promise(setImmediate);
 assert.equal(b.calls.filter(c=>c.data).length,0);
});

test('closing an active receiver sends a scoped unload event but preview never does',async()=>{
 const active=await browser();active.events.pagehide();await new Promise(setImmediate);
 const close=active.calls.filter(c=>c.path==='/surfaces/closed');assert.equal(close.length,1);assert.deepEqual(close[0].data,{transition_id:'transfer'});
 const preview=await browser('preview');preview.events.pagehide();await new Promise(setImmediate);assert.equal(preview.calls.filter(c=>c.path==='/surfaces/closed').length,0);
});

test('cutaway bounds are centered in the logical viewport',()=>{
 const points=[iso(0,0,6.4),iso(14,0),iso(14,9,-.4),iso(0,9)];
 for(const [axis,center] of [[0,480],[1,300]]){
  const values=points.map(p=>p[axis]);assert.ok(Math.abs((Math.min(...values)+Math.max(...values))/2-center)<.001);
 }
});
test('wall monitor renders a live notification title and body',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),texts=[];
 const c=new Proxy({fillText:text=>texts.push(text),measureText:text=>({width:text.length*6})},{get:(target,key)=>target[key]||(()=>{})});
 const room=new Room();room.background={};
 room.drawArchitecture(c,{server_time:1000,notification:{source:'system',title:'Monitor check',body:'Delivery confirmed'},return_location:{name:'Desk screen'},agenda:{events:[]}},null,1000);
 assert.ok(texts.includes('Monitor check'));assert.ok(texts.includes('Delivery confirmed'));assert.ok(texts.includes('DESK SCREEN'));
});

test('offline showcase art does not claim live health or show invalid dates',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),texts=[];
 const c=new Proxy({fillText:text=>texts.push(text),measureText:text=>({width:text.length*6})},{get:(target,key)=>target[key]||(()=>{})});
 const room=new Room();room.background={};
 room.drawArchitecture(c,{lab:{showcase:true}},null,1000);
 assert.ok(texts.includes('HELLO'));assert.ok(texts.includes('VOICE DEMO'));
 assert.ok(!texts.includes('ALL SYSTEMS CALM'));assert.ok(!texts.includes('Invalid Date'));
});

test('opposite spatial direction moves the lab doorway to the opposite wall',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),room=new Room();room.setDirection('right');
 assert.ok(iso(...anchors.door)[0]<iso(...anchors.center)[0]);
 assert.deepEqual(route('door','center')[0],anchors.door);
 room.setDirection('left');assert.ok(iso(...anchors.door)[0]>iso(...anchors.center)[0]);
});

test('Sonic avatar keeps sprite colors and a full quill/ear crop instead of human clothes',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),rectangles=[],images=[];
 const target={fillRect(...xy){rectangles.push({color:this.fillStyle,xy});},drawImage(...args){images.push(args);}};
 const c=new Proxy(target,{get:(object,key)=>object[key]||(()=>{})});
 const room=new Room();room.avatarSpec=require('../okabebot/characters/sonic/avatar.json');room.portraits=Array(6).fill({});
 room.avatar(c,[8,4],false,1000,{character:{style:'sonic'},presenter:{}});
 const colors=new Set(rectangles.map(r=>r.color));
 for(const color of ['#1765d1','#edc59c','#f5f4ed','#d93836'])assert.ok(colors.has(color));
 assert.ok(!colors.has('#283a48'));assert.ok(!colors.has('#2a3e4a'));
 const [,x,y,w,h]=images[0];assert.ok(x<=100&&y<=28&&x+w>=352&&y+h>=204);
});

test('morning layout clips and shifts room, draws a quarter-width rail, rotates without poll reset',()=>{
 const {Room}=require('../okabebot/web/lab-room.js');const r=new Room(),calls=[];
 const c=new Proxy({measureText:s=>({width:s.length*8})},{get:(o,k)=>k in o?o[k]:(...a)=>calls.push([k,...a]),set:(o,k,v)=>(o[k]=v,true)});
 r.renderScene=()=>calls.push(['scene']);
 const model={now:1000,state:{receivedAt:1000,server_time:1012,environment:{presentation:'room'},morning:{rotation_seconds:12,prepared_at:1000,cards:[{kind:'weather',title:'OUTSIDE',body:'Invented weather'},{kind:'calendar',title:'08:00',body:'Invented appointment'}]}}};
 r.render(c,model);assert.ok(calls.some(a=>a[0]==='translate'&&a[1]===-72));
 assert.ok(calls.some(a=>a[0]==='rect'&&a[3]===716));assert.ok(calls.some(a=>a[0]==='fillText'&&a[1]==='08:00'));
 assert.ok(calls.some(a=>a[0]==='fillRect'&&a[1]===728));
 assert.ok(calls.some(a=>a[0]==='fillText'&&a[1]==='OUTSIDE'));
 assert.equal(calls.filter(a=>a[0]==='fillRect'&&a[1]===728).length,2);
 calls.length=0;model.state.morning=null;r.render(c,model);assert.deepEqual(calls,[['scene']]);
});

test('live Cast page initializes its own audio but preview stays silent',async()=>{
 const live=await browser('tv',false,true);
 assert.equal(live.audioCalls.filter(c=>c[0]==='enable').length,1);
 assert.ok(live.audioCalls.some(c=>c[0]==='volume'&&c[1]===20));
 live.events.pagehide();assert.ok(live.audioCalls.some(c=>c[0]==='close'));
 const preview=await browser('preview',false,true);
 assert.equal(preview.audioCalls.filter(c=>c[0]==='enable').length,0);
});

test('blocked sound permission never blocks visual readiness or receiver heartbeat',async()=>{
 const b=await browser('tv',false,'blocked');
 assert.ok(b.calls.some(c=>c.path==='/surfaces/heartbeat'));
 assert.equal(b.nodes['#enable-sound'].hidden,false);
});

test('weather sprites cover conditions with authored pixels and time-based precipitation',()=>{
 const {weatherSprite}=require('../okabebot/web/lab-room.js');
 const frames=[];
 const c=new Proxy({fillRect(...xy){frames.push([this.fillStyle,...xy]);}},{get:(o,k)=>o[k]||(()=>{})});
 for(const condition of ['sunny','clear-night','partlycloudy','cloudy','fog','hail','lightning','lightning-rainy','pouring','rainy','snowy','snowy-rainy','windy','windy-variant','exceptional']){
  frames.length=0;assert.equal(weatherSprite(c,condition,0,0,0),condition);assert.ok(frames.length>=5);
  assert.ok(frames.every(row=>row.slice(1).every(Number.isInteger)));
 }
 frames.length=0;weatherSprite(c,'rainy',0,0,0);const a=JSON.stringify(frames);
 frames.length=0;weatherSprite(c,'rainy',0,0,250);assert.notEqual(JSON.stringify(frames),a);
 assert.equal(weatherSprite(c,'untrusted-not-a-condition',0,0,0),'exceptional');
});

test('TV expression follows local buffer and playback clock instead of early server speech',async()=>{
 const audioState={buffering:true};const screen=await browser('tv',false,true,audioState);
 screen.frame(150);assert.equal(screen.renders.at(-1).state.presenter.activity,'thinking');
 audioState.buffering=false;audioState.presenter={activity:'speaking',start_at:123,envelope:[.2,.4]};
 screen.frame(200);assert.deepEqual(screen.renders.at(-1).state.presenter,audioState.presenter);
});

test('notification presentation survives fresh polls, withdraws private text and resets on disconnect',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),room=new Room();
 const item={source:'calendar',title:'Synthetic appointment',body:'Invented details'};
 assert.equal(room.presentation({notification:item},1000).notification_progress,0);
 const half=room.presentation({notification:{...item}},1250);assert.equal(half.notification_progress,.5);
 assert.equal(room.presentation(half,1250),half); // Shared compact/avatar path samples once.
 assert.equal(room.presentation({notification:item},1500).notification_progress,1);
 const withdrawn=room.presentation({},1550);assert.equal(withdrawn.notification.body,'');
 assert.ok(room.presentation({},1700).notification_progress<1);
 assert.equal(room.presentation({},1900).notification,null);
 room.presentation({notification:item},2000);room.clearPresentation();
 assert.equal(room.presentation({},2001).notification,null);
});
test('reduced-motion notifications settle on the same frame without changing input',()=>{
 const {Room}=require('../okabebot/web/lab-room.js'),room=new Room();
 const state={notification:{title:'Synthetic'},motion:{reduced_motion:true}};
 assert.equal(room.presentation(state,1000).notification_progress,1);
 assert.equal(state.notification_progress,undefined);
 assert.equal(room.presentation({motion:{reduced_motion:true}},1100).notification,null);
});
