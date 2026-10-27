/* Optional documentation renderer: NODE_PATH must provide @napi-rs/canvas.
   Inputs are code-drawn character frames, never private reference recordings. */
const fs=require('node:fs'),{createCanvas}=require('@napi-rs/canvas');
global.document={createElement:()=>createCanvas(480,320)};
const {Room,W,H}=require('../okabebot/web/lab-room.js');
const style=process.argv[4]||'kurisu';const room=new Room();room.setAssets(JSON.parse(fs.readFileSync(process.argv[2],'utf8')),style);
const canvas=createCanvas(W,H),now=1000;
room.render(canvas.getContext('2d'),{now,position:[8,4],walking:false,visible:true,opacity:1,focus:null,state:{phase:'preview',server_time:1782498600,receivedAt:now,character:{style},lab:{title:'Little Lab'},return_location:{name:'Companion display'},presenter:{},notification:{source:'github',title:'Build finished',body:'Ready to review.'},focus:{active:false},agenda:{stale:false,events:[]},deployments:[]}});
fs.writeFileSync(process.argv[3],canvas.toBuffer('image/png'));
