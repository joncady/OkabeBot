/* Optional documentation image using the actual compact surface avatar. */
const fs=require('node:fs'),{createCanvas}=require('@napi-rs/canvas');
global.document={createElement:()=>createCanvas(480,320)};
const {Room,iso}=require('../okabebot/web/lab-room.js'),room=new Room();
const style=process.argv[4]||'kurisu';room.setAssets(JSON.parse(fs.readFileSync(process.argv[2],'utf8')),style);
const canvas=createCanvas(320,320),ctx=canvas.getContext('2d');ctx.fillStyle='#101b27';ctx.fillRect(0,0,320,320);
room.idleEnvironment(ctx,1000,{character:{style}});
const p=iso(8,4);ctx.save();ctx.translate(160,278);ctx.scale(2.6,2.6);ctx.translate(-p[0],-p[1]);room.avatar(ctx,[8,4],false,1000,{character:{style},presenter:{}},1);ctx.restore();
fs.writeFileSync(process.argv[3],canvas.toBuffer('image/png'));
