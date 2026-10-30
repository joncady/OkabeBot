const test=require('node:test'),assert=require('node:assert/strict');
const {focusState,focusBadge,Room}=require('../okabebot/web/lab-room.js');
function state(values={}){return{phase:'tv',server_time:1000,receivedAt:100,focus:{active:true,ends_at:1060},presenter:{activity:'idle'},...values};}
function canvas(){const calls=[];const c=new Proxy({calls},{get(target,name){if(name in target)return target[name];return(...args)=>calls.push([name,...args]);},set(target,name,value){target[name]=value;return true;}});return c;}
test('focus countdown follows server receipt clock and expires without another callback',()=>{
 assert.equal(focusState(state(),100).remaining_seconds,60);
 assert.equal(focusState(state(),59100).remaining_seconds,1);
 assert.equal(focusState(state(),60100).active,false);
 for(const f of [{active:true,ends_at:Infinity},{active:true,ends_at:'1060'},{active:true,ends_at:20000},{active:1,ends_at:1060}])assert.equal(focusState(state({focus:f}),100).active,false);
});
test('focus yields to speaking/listening, notifications, media hint, deployment and travel',()=>{
 for(const values of [{presenter:{activity:'speaking'}},{presenter:{activity:'listening'}},{presenter:{activity:'thinking'}},{notification:{title:'Notice'}},{focus:{active:true,ends_at:1060,ambient_allowed:false}},{deployments:[{}]},{phase:'leaving_tv'},{phase:'entering_tv'}]){
  const c=canvas();assert.equal(focusBadge(c,state(values),100),false);assert.equal(c.calls.length,0);
 }
 assert.equal(focusBadge(canvas(),state(),100,true),false);
});
test('compact badge paints only its small corner and clears no transparent character canvas',()=>{
 const c=canvas();assert.equal(focusBadge(c,state(),100),true);
 assert.ok(c.calls.some(x=>x[0]==='fillText'&&x[1]==='1:00'));
 assert.ok(!c.calls.some(x=>x[0]==='clearRect'));
 for(const [kind,x,y,w,h] of c.calls.filter(x=>x[0]==='fillRect')){assert.ok(x>=208&&x+w<=312);assert.ok(y>=8&&y+h<=40);}
});
test('room actor keeps explicit speaking envelope while focus is active',()=>{
 const room=new Room();room.portraits=[0,1,2,3,4,5];
 const c=canvas();const s=state({character:{style:'okabe'},presenter:{activity:'speaking',start_at:1000,envelope:[1]},serverOffset:1000*1000-Date.now()});
 room.avatar(c,[8,4],false,100,s);
 const image=c.calls.find(x=>x[0]==='drawImage');assert.equal(image[1],2);
});
test('full-scene environments without monitors still render focus countdown',()=>{
 for(const set of ['green-hill','star-light','rooftop-garden']){
  const room=new Room(),c=canvas();room.portraits=[];
  room.render(c,{state:state({character:{style:'sonic'},environment:{set,presentation:'room'}}),now:100,visible:true,position:[8,4],walking:false,opacity:1});
  assert.ok(c.calls.some(x=>x[0]==='fillText'&&x[1]==='1:00'),set);
 }
});
