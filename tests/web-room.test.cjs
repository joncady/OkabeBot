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
async function browser(phase='tv',broken=false){
 const calls=[],events={},nodes={};
 function node(id){return nodes[id]||=( {textContent:'',classList:{toggle(){}},setAttribute(){},addEventListener(){},focus(){},getContext(){return {clearRect(){}};}} );}
 const state={phase,remote_controls:true,transition_id:'transfer',duration_seconds:2,visibility_lease_seconds:6,character:{style:'okabe',name:'Companion'},lab:{title:'Custom room'},return_location:{name:'Desk nook'},destination_name:'Den screen',server_time:1000};
 const context={console,LabRoom:{Room:class{constructor(){this.actor={position:[8,4],transfer(){return [[1,1],[2,2]];}};}setAssets(){}render(){if(broken)throw Error("Broken renderer");}}},location:{hash:'#scoped',reload(){}},performance:{now:()=>100},Date,requestAnimationFrame(){},setTimeout(){},document:{getElementById:id=>node("#"+id),querySelector:selector=>node(selector),addEventListener:(event,fn)=>events[event]=fn},window:{addEventListener:(event,fn)=>events[event]=fn},fetch:async(path,options)=>{calls.push({path,data:options.body&&JSON.parse(options.body)});return{ok:true,json:async()=>path==='/surfaces/state'?state:{frames:[[]]}};}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/tv.js','utf8'),context);await new Promise(setImmediate);return{calls,events,nodes};
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
 const room=new Room();room.portraits=Array(6).fill({});
 room.avatar(c,[8,4],false,1000,{character:{style:'sonic'},presenter:{}});
 const colors=new Set(rectangles.map(r=>r.color));
 for(const color of ['#1765d1','#edc59c','#f5f4ed','#d93836'])assert.ok(colors.has(color));
 assert.ok(!colors.has('#283a48'));assert.ok(!colors.has('#2a3e4a'));
 const [,x,y,w,h]=images[0];assert.ok(x<=100&&y<=28&&x+w>=352&&y+h>=204);
});
