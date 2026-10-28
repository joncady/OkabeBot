/* Verify the destination layers reconstruct each original room frame. No devices. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),{createCanvas,loadImage}=require('@napi-rs/canvas');
async function main(){
 const directory=process.argv[2];if(!directory)throw Error('Use check-alexa-layers.cjs artwork-directory');
 const canvas=createCanvas(960,540),ctx=canvas.getContext('2d'),background=await loadImage(path.join(directory,'background.png'));
 const results=[];
 for(const name of ['idle.png','talk-a.png','talk-b.png','blink.png']){
  const actor=await loadImage(path.join(directory,'actor-'+name));
  ctx.clearRect(0,0,960,540);ctx.drawImage(actor,0,0);
  const actorPixels=ctx.getImageData(0,0,960,540).data;
  let transparent=0;for(let i=3;i<actorPixels.length;i+=4)if(actorPixels[i]===0)transparent++;
  ctx.clearRect(0,0,960,540);ctx.drawImage(background,0,0);ctx.drawImage(actor,0,0);
  const composite=ctx.getImageData(0,0,960,540).data;
  ctx.clearRect(0,0,960,540);ctx.drawImage(await loadImage(path.join(directory,name)),0,0);
  const original=ctx.getImageData(0,0,960,540).data;
  let changed=0;for(let i=0;i<composite.length;i+=4)if(composite.slice(i,i+4).some((v,j)=>Math.abs(v-original[i+j])>2))changed++;
  const row={frame:name,changedPixels:changed,transparentFraction:transparent/(960*540)};results.push(row);
  if(changed||row.transparentFraction<.8)process.exitCode=1;
 }
 console.log(JSON.stringify({scene:JSON.parse(fs.readFileSync(path.join(directory,'scene.json'),'utf8')),results}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
