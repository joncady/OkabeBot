/* Export generic APL scene frames from the existing room/character renderer.
   NODE_PATH must provide @napi-rs/canvas. Never reads live household data. */
const fs=require('node:fs'),path=require('node:path'),{createCanvas}=require('@napi-rs/canvas');
global.document={createElement:()=>createCanvas(480,320)};
const {Room,iso}=require('../okabebot/web/lab-room.js');
const [assetsFile,output,style='okabe',set='pixel-lab']=process.argv.slice(2);
if(!assetsFile||!output||!require('./character-catalog.cjs').scenes.characters[style])throw Error('Use assets.json output-directory [character]');
fs.mkdirSync(output,{recursive:true});
const room=new Room();room.setAssets(JSON.parse(fs.readFileSync(assetsFile,'utf8')),style);
const catalog=require('./character-catalog.cjs').scenes;
const original=room.avatar;
let actorClock=null;
room.avatar=function(c,position,...args){if(actorClock!==null)args[1]=actorClock;const p=iso(...position);c.save();c.translate(...p);c.scale(1.5,1.5);c.translate(-p[0],-p[1]);original.call(this,c,position,...args);c.restore();};
for(const [file,mouth,now] of [['idle.png',0,1000],['talk-a.png',.5,1000],['talk-b.png',1,1000],['blink.png',0,4600]]){
 actorClock=now;
 const canvas=createCanvas(960,540),ctx=canvas.getContext('2d');ctx.translate(0,-30);
 const current=Date.now()/1000;
 const state={character:{style},environment:{set,name:catalog.sets[set]?.name,presentation:'room',assigned:true},lab:{title:'LITTLE LAB',showcase:true},return_location:{name:'COMPANION'},notification:null,focus:{active:false},agenda:{stale:false,events:[]},deployments:[],presenter:{activity:mouth?'speaking':'idle',start_at:current-1,envelope:Array(100).fill(mouth)}};
 room.render(ctx,{now:1000,position:[8,4],walking:false,visible:true,opacity:1,focus:null,state});
 fs.writeFileSync(path.join(output,file),canvas.toBuffer('image/png'));
}
// Session destination layers keep the room fixed when the actor is hidden/moved.
const layerState={character:{style},environment:{set,name:catalog.sets[set]?.name,presentation:'room',assigned:true},lab:{title:'LITTLE LAB',showcase:true},return_location:{name:'COMPANION'},notification:null,focus:{active:false},agenda:{stale:false,events:[]},deployments:[],presenter:{activity:'idle'}};
const background=createCanvas(960,540),bc=background.getContext('2d');bc.translate(0,-30);
room.render(bc,{now:1000,position:[8,4],walking:false,visible:false,opacity:1,focus:null,state:layerState});
fs.writeFileSync(path.join(output,'background.png'),background.toBuffer('image/png'));
for(const [file,mouth,now] of [['actor-idle.png',0,1000],['actor-talk-a.png',.5,1000],['actor-talk-b.png',1,1000],['actor-blink.png',0,4600]]){
 actorClock=now;
 const canvas=createCanvas(960,540),ctx=canvas.getContext('2d');ctx.translate(0,-30);
 const current=Date.now()/1000;
 const state={...layerState,presenter:{activity:mouth?'speaking':'idle',start_at:current-1,envelope:Array(100).fill(mouth)}};
 room.avatar(ctx,[8,4],false,now,state,1);
 fs.writeFileSync(path.join(output,file),canvas.toBuffer('image/png'));
}
const small=createCanvas(320,320),c=small.getContext('2d'),state={character:{style},environment:{set,presentation:'companion',assigned:true},presenter:{}};
room.idleEnvironment(c,1000,state);const p=iso(8,4);c.save();c.translate(160,278);c.scale(2.6,2.6);c.translate(-p[0],-p[1]);original.call(room,c,[8,4],false,1000,state,1);c.restore();
fs.writeFileSync(path.join(output,'companion.png'),small.toBuffer('image/png'));
