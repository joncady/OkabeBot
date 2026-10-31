/* Character-owned scenery; adapters and movement never draw environment pixels. */
(function(root){
'use strict';
function theme(character,environment){return environment?.set||(character?.style==='sonic'?'green-hill':'pixel-lab');}
function rect(c,x,y,w,h,color){c.fillStyle=color;c.fillRect(Math.round(x),Math.round(y),w,h);}
function polygon(c,points,color){c.fillStyle=color;c.beginPath();c.moveTo(...points[0]);for(const p of points.slice(1))c.lineTo(...p);c.closePath();c.fill();}
function palm(c,x,y,scale=1){
 c.save();c.translate(x,y);c.scale(scale,scale);
 for(let i=0;i<8;i++)rect(c,-3+i*.5,-i*5,7,5,i%2?'#b56b36':'#d28d49');
 for(const [dx,dy,w,h] of [[-28,-42,25,5],[-22,-48,23,5],[0,-46,24,5],[14,-40,18,5],[-8,-55,7,18],[5,-53,7,15],[-29,-37,7,10],[26,-35,5,11]])rect(c,dx,dy,w,h,'#258c43');
 rect(c,-2,-41,8,6,'#9d602e');c.restore();
}
function sunflower(c,x,y,t){
 const sway=Math.round(Math.sin(t/1800));rect(c,x,y-22,3,22,'#237a3b');rect(c,x-7,y-12,8,3,'#4bba44');
 for(const [dx,dy,w,h] of [[-7,-31,6,7],[5,-31,6,7],[-1,-37,6,6],[-1,-24,6,6]])rect(c,x+dx+sway,y+dy,w,h,'#f8dc50');
 rect(c,x-1+sway,y-31,7,7,'#b96b30');
}
function compact(c,now,opacity=1,set='green-hill'){
 if(set==='pocket-nook'){
  c.save();c.globalAlpha=opacity;
  rect(c,59,226,56,46,'#536779');rect(c,64,231,46,34,'#264c64');
  rect(c,69,248,12,17,'#457b87');rect(c,85,239,16,26,'#72a3a0');rect(c,64,260,46,5,'#b6d9bb');
  rect(c,59,272,202,8,'#d3b183');rect(c,65,280,190,18,'#79647d');
  rect(c,69,298,10,8,'#4a405a');rect(c,239,298,10,8,'#4a405a');
  rect(c,224,249,27,23,'#bc805f');rect(c,231,244,13,5,'#d3b183');
  rect(c,228,256,19,3,'#e1c69b');rect(c,236,256,3,9,'#e1c69b');
  c.restore();return;
 }
 if(set==='mac-desk'){
  c.save();c.globalAlpha=opacity;
  rect(c,60,275,200,7,'#b59473');rect(c,64,282,192,12,'#5c5160');
  rect(c,72,294,10,12,'#5c5160');rect(c,238,294,10,12,'#5c5160');
  rect(c,68,238,46,30,'#283b4b');rect(c,72,242,38,22,'#78babb');
  rect(c,88,268,7,7,'#9ba9a4');rect(c,79,273,26,3,'#9ba9a4');
  rect(c,76,247,18,2,'#d2eee2');rect(c,76,253,28,2,'#498e9b');
  rect(c,222,256,16,19,'#e5d2a5');rect(c,238,260,5,9,'#e5d2a5');
  rect(c,225,254,10,4,'#655045');c.restore();return;
 }
 if(set!=='green-hill'){
  c.save();c.globalAlpha=opacity;
  const cafe=set==='maid-cafe',roof=set==='rooftop-garden',night=set==='star-light';
  const wood=cafe?'#805440':roof?'#587568':night?'#38365b':'#466570';
  rect(c,64,274,192,19,wood);rect(c,72,293,12,12,wood);rect(c,236,293,12,12,wood);
  rect(c,64,271,192,5,night?'#dc79bb':roof?'#94b47b':'#b99e76');
  if(cafe){rect(c,74,249,17,22,'#ece0be');rect(c,91,254,5,10,'#ece0be');rect(c,77,246,11,4,'#634737');rect(c,226,239,22,32,'#3b514b');rect(c,230,244,14,3,'#cddab1');}
  else if(roof){sunflower(c,80,271,now);sunflower(c,238,271,now+700);rect(c,69,271,24,8,'#ab7454');rect(c,227,271,24,8,'#ab7454');}
  else if(night){rect(c,77,230,5,41,'#8084a5');rect(c,71,226,17,8,'#f4d48b');rect(c,232,233,5,38,'#8084a5');rect(c,226,229,17,8,'#f4d48b');}
  else{rect(c,72,244,21,25,'#8fbec3');rect(c,76,248,13,13,'#243e51');rect(c,232,242,9,28,'#9bc8c1');rect(c,226,258,22,12,'#6faaa4');}
  c.restore();return;
 }
 c.save();c.globalAlpha=opacity;
 // Small transparent diorama leaves the character and desktop breathing room.
 polygon(c,[[54,274],[83,263],[239,263],[267,275],[244,304],[79,304]],'#88512c');
 for(let row=0;row<3;row++)for(let col=0;col<10;col++){
  const x=73+col*17,y=276+row*9;
  if(x+17<=250)rect(c,x,y,17,9,(row+col)%2?'#a76735':'#cb8948');
 }
 polygon(c,[[54,274],[83,263],[239,263],[267,275],[239,284],[81,284]],'#21843c');
 rect(c,74,267,174,5,'#72cf45');rect(c,63,272,194,5,'#43af3c');
 for(let i=0;i<12;i++)rect(c,72+i*15,276,7,4,'#3ba03b');
 palm(c,79,270,.85);sunflower(c,239,269,now);
 for(const x of [100,218]){c.strokeStyle='#f4d351';c.lineWidth=3;c.strokeRect(x,249,8,12);}
 c.restore();
}
function board(c,s,set='green-hill'){
 c.save();c.translate(180,-20);
 const note=s.notification,event=s.agenda?.events?.[0];
 if(!note&&!event){rect(c,98,286,8,63,'#91562d');rect(c,75,251,132,36,'#91562d');rect(c,80,256,122,26,'#d9b374');c.fillStyle='#413e2c';c.font='12px monospace';c.fillText(set==='star-light'?'STAR LIGHT':set==='rooftop-garden'?'ROOFTOP':'GREEN HILL',86,274);c.restore();return;}
 rect(c,92,291,10,132,'#91562d');rect(c,346,291,10,132,'#91562d');
 rect(c,78,190,292,151,'#75482d');rect(c,85,197,278,136,'#c99a58');rect(c,90,202,268,126,'#ebd5a1');
 c.fillStyle='#413e2c';c.font='bold 17px monospace';c.textAlign='left';
 const title=note?.title||event?.title||'GREEN HILL';
 const words=title.split(/\s+/);let line='',y=226;
 for(const word of words){const next=line?line+' '+word:word;if(c.measureText(next).width>242&&line){c.fillText(line,102,y);line=word;y+=22;if(y>270)break;}else line=next;}
 if(y<=270)c.fillText(line,102,y);
 const detail=note?.body||(!note&&event?new Date(event.start*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'');
 if(detail){c.font='12px monospace';c.fillText(detail.slice(0,32),102,310);}
 else{c.strokeStyle='#8b7446';c.lineWidth=3;for(let i=0;i<3;i++)c.strokeRect(126+i*65,282,18,25);}
 c.restore();
}
function room(c,model,room,iso,doorAnchor,set='green-hill'){
 const {state:s,now,visible,position,walking,opacity=1}=model;
 const night=set==='star-light',roof=set==='rooftop-garden';
 rect(c,0,0,960,600,night?'#192139':roof?'#d1b9a2':'#8bd1ef');
 if(night||roof){
  for(let i=0;i<18;i++){const x=i*60-35,h=75+(i*37)%130;rect(c,x,300-h,52,h,night?'#29364c':'#887f84');for(let y=310-h;y<285;y+=19)for(let dx=7;dx<48;dx+=13)rect(c,x+dx,y,4,7,night?'#d5c79c':'#c1afa3');}
  if(night)for(let i=0;i<35;i++)rect(c,(i*97)%960,20+(i*43)%145,2,2,'#b8cecc');
 }
 for(let i=0;i<4;i++){
  const x=((i*270+now/350)%1160)-160;
  if(!night){rect(c,x,62+(i%2)*45,72,12,'#e9f3d8');rect(c,x+16,50+(i%2)*45,36,15,'#e9f3d8');}
 }
 for(const [x,y,w,h] of [[-50,210,290,140],[240,160,270,180],[570,180,370,180]]){
  if(!night&&!roof){polygon(c,[[x,y+h],[x+w*.25,y+30],[x+w*.5,y],[x+w*.75,y+30],[x+w,y+h]],'#439c73');
  polygon(c,[[x+30,y+h],[x+w*.35,y+50],[x+w*.6,y+20],[x+w-20,y+h]],'#64ba76');}
 }
 const a=iso(0,0),b=iso(14,0),d=iso(0,9),e=iso(14,9);
 polygon(c,[d,e,[e[0],e[1]+65],[d[0],d[1]+65]],night?'#373c50':roof?'#465a55':'#87532f');
 c.save();c.beginPath();c.moveTo(...d);c.lineTo(...e);c.lineTo(e[0],e[1]+65);c.lineTo(d[0],d[1]+65);c.closePath();c.clip();
 for(let y=350;y<600;y+=20)for(let x=0;x<960;x+=20)rect(c,x,y,20,20,(Math.floor(x/20)+Math.floor(y/20))%2?(night?'#373c50':roof?'#465a55':'#a76837'):(night?'#40465c':roof?'#536a62':'#cd8c4b'));c.restore();
 polygon(c,[a,b,e,d],night?'#4b4d66':roof?'#667e74':'#40a84b');
 for(let x=0;x<14;x++)for(let y=0;y<9;y++)if((x+y)%2===0)polygon(c,[iso(x,y),iso(x+1,y),iso(x+1,y+1),iso(x,y+1)],night?'#565873':roof?'#71897f':'#49b74c');
 if(!night&&!roof)for(let i=0;i<14;i++){const p=iso(i,9);rect(c,p[0],p[1],18,6,'#82d745');}
 const palms=[iso(11,1),iso(1,2)],flower=iso(13,6);
 if(night){for(const p of palms){rect(c,p[0],p[1]-90,7,90,'#8c91a8');rect(c,p[0]-12,p[1]-94,31,12,'#edca8a');}}
 else if(roof){for(const p of palms){rect(c,p[0]-22,p[1]-8,48,18,'#9e745c');sunflower(c,p[0],p[1]-8,now);sunflower(c,p[0]+15,p[1]-8,now+900);}}
 else{palm(c,...palms[0],2.5);palm(c,...palms[1],1.5);sunflower(c,...flower,now);}
 board(c,s,set);
 const door=iso(...doorAnchor);
 c.strokeStyle='#ffdc55';c.lineWidth=6;c.strokeRect(door[0]-16,door[1]-58,32,52);
 if(visible)room.avatar(c,position,walking,now,s,opacity);
}
const api={theme,compact,room};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CharacterEnvironments=api;
})(typeof window==='undefined'?{}:window);
