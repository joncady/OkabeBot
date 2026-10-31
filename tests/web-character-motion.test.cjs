const test=require('node:test'),assert=require('node:assert/strict');
const {Room,sampleMotion}=require('../okabebot/web/lab-room.js');
const data=require('../scripts/character-catalog.cjs').motion;
test('work poses yield to conversation, focus/media and stale display leases',()=>{
 const room=new Room();room.motionCatalog=data;room.avatarSpec=require('../okabebot/characters/kurisu/avatar.json');room.portraits=Array(6).fill({});
 const poses=[];room.action=(_,pose)=>poses.push(pose);room.workbench=(_,pose)=>poses.push(pose);
 const c=new Proxy({},{get:()=>()=>{}});
 const base={receivedAt:1000,character:{style:'kurisu'},presenter:{activity:'idle'},work:{stage:'drafting',elapsed_seconds:2,lease_seconds:8}};
 room.avatar(c,[8,4],false,2000,base);assert.equal(poses.pop(),'write');
 for(const change of [{presenter:{activity:'thinking'}},{notification:{}},{focus:{ambient_allowed:false}},{motion:{reduced_motion:true}}]){
  room.avatar(c,[8,4],false,2000,{...base,...change});assert.equal(poses.pop(),'rest');
 }
 room.avatar(c,[8,4],false,10000,base);assert.equal(poses.pop(),'rest');
});
test('all authored action poses retain balanced canvas transforms and finite geometry',()=>{
 const room=new Room();
 for(const style of Object.keys(data.characters))for(const stage of Object.keys(data.work_stages))for(const at of [0,.1,.3,1,3,6]){
  let depth=0;
  const c=new Proxy({globalAlpha:1,save(){depth++;},restore(){depth--;},fillRect(...v){assert.ok(v.every(Number.isFinite));assert.ok(v[2]>=0&&v[3]>=0);},translate(...v){assert.ok(v.every(Number.isFinite));}},{get:(o,k)=>k in o?o[k]:()=>{}});
  const motion=sampleMotion(data,style,at,'idle',false,stage);
  room.action(c,motion.pose,motion,require('../okabebot/characters/'+style+'/avatar.json'),at*1000);assert.equal(depth,0);
 }
});
test('golden workbench draws foreground monitor after the face and keeps eye tracking above it',()=>{
 for(const style of ['okabe','kurisu']){
  const room=new Room();room.motionCatalog=data;room.avatarSpec=require('../okabebot/characters/'+style+'/avatar.json');room.portraits=Array(6).fill({});
  const calls=[];let depth=0;
  const c=new Proxy({globalAlpha:1,save(){depth++;},restore(){depth--;},drawImage(){calls.push(['face']);},fillRect(...v){calls.push([this.fillStyle,...v]);assert.ok(v.every(Number.isFinite));},measureText(){return {width:0};}},{get:(o,k)=>k in o?o[k]:()=>{}});
  room.avatar(c,[8,4],false,2000,{receivedAt:2000,character:{style},presenter:{},work:{stage:'researching',elapsed_seconds:1.7,lease_seconds:8}});
  const face=calls.findIndex(v=>v[0]==='face'),monitor=calls.findIndex(v=>v[0]==='#1d303d'&&v[1]===-23);
  assert.ok(monitor>face);assert.ok(calls[monitor][2]>-60);assert.equal(depth,0);
  assert.ok(room.avatarSpec.head.eyes.length===2);
 }
});
