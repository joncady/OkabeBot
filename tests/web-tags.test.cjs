const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function fixture(options={}){
 const nodes={},calls=[];let token='synthetic-owner';
 const node=()=>({hidden:false,value:'',checked:true,children:[],textContent:'',append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},set innerHTML(v){throw Error('No HTML parsing');}});
 const get=id=>nodes[id]||=(node());get('dashboard-forget').onclick=()=>{token='';};
 let chores=options.chores||[],state={mappings:options.mappings||[],locations:[{id:'desk',name:'Example desk'}],learning:false,learned:null};
 const context={crypto:require("node:crypto").webcrypto,document:{getElementById:get,createElement:node},dashboardAccess:{token:()=>token},JSON,Date,URL,setInterval(){},
 fetch:async(path,opts)=>{calls.push({path,opts});const data=opts.body?JSON.parse(opts.body):{};
 if(path==='/tags/learn')state={...state,learning:true,learned:'synthetic-tag'};
 if(path==='/chores')return{ok:true,json:async()=>({items:chores})};
 if(path==='/chores/save'){const item={...data,id:data.id,due_at:2000000};chores=[...chores.filter(x=>x.id!==item.id),item];return{ok:true,json:async()=>({item,items:chores})};}
 if(path==='/chores/complete')return{ok:true,json:async()=>({items:chores})};
 if(path==='/tags/save'){
  if(options.failBinding)return{ok:false,json:async()=>({error:'Mapping failed'})};
  state={...state,chores,learning:false,mappings:[{...data,action:data.action||'call_companion'}]};
 }
 if(path==='/tags')state={...state,chores};
 return{ok:true,json:async()=>state};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/tags.js','utf8')+'\nglobalThis.ui=tagsUI;',context);
 await new Promise(r=>setImmediate(r));return{nodes,calls,context,unmapped(){state={...state,last_scan:{tag_id:"second-synthetic",at:1000,status:"unmapped_or_disabled"}};}};
}
test('learn captures tag without saving or invoking movement, save uses selected destination',async()=>{
 const f=await fixture();await f.nodes['tag-register'].onclick();await new Promise(r=>setImmediate(r));
 assert.equal(f.nodes['tag-id'].value,'synthetic-tag');assert.equal(f.calls.filter(c=>c.path==='/tags/save').length,0);
 f.nodes['tag-name'].value='<img src=x>';f.nodes['tag-location'].value='desk';
 f.nodes['tag-form'].onsubmit({preventDefault(){}});await new Promise(r=>setImmediate(r));
 const call=f.calls.find(c=>c.path==='/tags/save');assert.equal(JSON.parse(call.opts.body).location_id,'desk');
 assert.equal(f.nodes['tag-mappings'].children[0].children[0].textContent,'<img src=x>');
 assert.ok(f.calls.every(c=>c.opts.headers['X-Hardware-Token']==='synthetic-owner'));
 assert.ok(f.calls.every(c=>!c.path.includes('synthetic-owner')));
});
test('forget owner access clears rendered tag mappings and captured IDs',async()=>{
 const f=await fixture();await f.nodes['tag-register'].onclick();await new Promise(r=>setImmediate(r));
 f.nodes['dashboard-forget'].onclick();assert.equal(f.nodes['nfc-tags'].hidden,true);
 assert.equal(f.nodes['tag-id'].value,'');assert.equal(f.nodes['tag-mappings'].children.length,0);
});
test('new registration clears the previous captured ID before waiting for another scan',async()=>{
 const f=await fixture();f.context.document.getElementById('tag-id').value='previous-tag';f.context.document.getElementById('tag-name').value='Old mapping';
 const pending=f.nodes['tag-register'].onclick();assert.equal(f.nodes['tag-id'].value,'');assert.equal(f.nodes['tag-save'].disabled,true);
 await pending;await new Promise(r=>setImmediate(r));assert.equal(f.nodes['tag-id'].value,'synthetic-tag');assert.equal(f.nodes['tag-save'].disabled,false);
});

test('unmapped scan can be loaded into the mapping form without scanning or moving again',async()=>{
 const f=await fixture();f.unmapped();await f.context.ui.load();assert.equal(f.nodes['tag-map-last'].hidden,false);
 f.nodes['tag-map-last'].onclick();assert.equal(f.nodes['tag-id'].value,'second-synthetic');assert.equal(f.nodes['tag-save'].disabled,false);
 assert.equal(f.calls.filter(c=>c.path==='/tags/test'||c.path==='/tags/save').length,0);
});


test('chore action saves a configurable interval and binds its stable ID without marking done',async()=>{
 const f=await fixture();await f.nodes['tag-register'].onclick();
 f.nodes['tag-name'].value='Change towels';f.nodes['tag-action'].value='chore_reminder';f.nodes['tag-action'].onchange();
 assert.equal(f.nodes['tag-destination'].hidden,true);assert.equal(f.nodes['tag-location'].required,false);
 f.nodes['tag-chore-delay'].value='2';f.nodes['tag-chore-unit'].value='weeks';f.nodes['tag-chore-repeat'].value='3';
 await f.nodes['tag-form'].onsubmit({preventDefault(){}});
 const saved=JSON.parse(f.calls.find(c=>c.path==='/chores/save').opts.body);
 assert.equal(saved.title,'Change towels');assert.equal(saved.interval_days,14);assert.equal(saved.repeat_days,3);assert.match(saved.id,/^[0-9a-f]{32}$/);
 const mapping=JSON.parse(f.calls.find(c=>c.path==='/tags/save').opts.body);
 assert.equal(mapping.action,'chore_reminder');assert.equal(mapping.chore_id,saved.id);assert.equal('location_id' in mapping,false);
 assert.equal(f.calls.filter(c=>c.path==='/chores/complete').length,0);
 const mark=f.nodes['tag-mappings'].children[0].children.find(n=>n.textContent==='Mark done');await mark.onclick();
 assert.equal(f.calls.filter(c=>c.path==='/chores/complete').length,1);assert.equal(f.calls.filter(c=>c.path==='/tags/test').length,0);
});

test('a failed tag bind reuses its saved chore ID on retry and double submit is ignored',async()=>{
 const options={failBinding:true},f=await fixture(options);await f.nodes['tag-register'].onclick();
 f.nodes['tag-name'].value='Synthetic chore';f.nodes['tag-action'].value='chore_reminder';f.nodes['tag-chore-delay'].value='5';f.nodes['tag-chore-unit'].value='days';
 const first=f.nodes['tag-form'].onsubmit({preventDefault(){}});await f.nodes['tag-form'].onsubmit({preventDefault(){}});await first;
 assert.equal(f.calls.filter(c=>c.path==='/chores/save').length,1);
 options.failBinding=false;await f.nodes['tag-form'].onsubmit({preventDefault(){}});
 const bodies=f.calls.filter(c=>c.path==='/chores/save').map(c=>JSON.parse(c.opts.body));assert.equal(bodies.length,2);assert.equal(bodies[0].id,bodies[1].id);
});

test('editing a chore tag keeps ID and cadence, renders titles literally and forget clears fields',async()=>{
 const item={id:'a'.repeat(32),title:'<svg onload=alert(1)>',interval_days:21,repeat_days:2,enabled:false};
 const f=await fixture({chores:[item],mappings:[{tag_id:'synthetic-tag',name:'Towel rack',action:'chore_reminder',chore_id:item.id,enabled:true}]});
 const row=f.nodes['tag-mappings'].children[0];assert.ok(row.children[1].textContent.includes(item.title));
 await row.children.find(n=>n.textContent==='Edit').onclick();
 assert.equal(f.nodes['tag-chore-select'].value,item.id);assert.equal(f.nodes['tag-chore-delay'].value,3);assert.equal(f.nodes['tag-chore-unit'].value,'weeks');assert.equal(f.nodes['tag-chore-reminders'].checked,false);
 f.nodes['dashboard-forget'].onclick();assert.equal(f.nodes['tag-chore-title'].value,'');assert.equal(f.nodes['tag-chore-select'].children.length,0);
});
test('inherited HA room labels render literally and refresh is owner initiated',async()=>{
 const f=await fixture({mappings:[{tag_id:'tag-a',name:'Towel chore',action:'call_companion',location_id:'desk',enabled:true,area_status:'assigned',ha_area:{area_id:'bath',room:'<bathroom>',floor:'Upper'}}]});
 const card=f.nodes['tag-mappings'].children[0];
 assert.ok(card.children.some(n=>n.textContent==='Room · Upper / <bathroom> · from Home Assistant'));
 assert.equal(f.calls.filter(c=>c.path==='/tags/refresh-areas').length,0);
 await f.nodes['tag-refresh-areas'].onclick();
 assert.equal(f.calls.filter(c=>c.path==='/tags/refresh-areas').length,1);
});
test('room check-in is explicitly saved without a fixed destination or synthetic scan',async()=>{
 const f=await fixture();await f.nodes['tag-register'].onclick();f.nodes['tag-id'].value='selected-tag';f.nodes['tag-name'].value='Room cue';f.nodes['tag-action'].value='room_checkin';f.nodes['tag-room-minutes'].value='5';f.nodes['tag-room-location'].value='';
 f.nodes['tag-action'].onchange();assert.equal(f.nodes['tag-destination'].hidden,true);
 await f.nodes['tag-form'].onsubmit({preventDefault(){}});
 const saved=JSON.parse(f.calls.find(c=>c.path==='/tags/save').opts.body);
 assert.equal(saved.action,'room_checkin');assert.equal(saved.room_follow,true);assert.equal(saved.room_minutes,5);assert.equal('location_id' in saved,false);
 assert.equal(f.calls.filter(c=>['/tags/source','/tags/test'].includes(c.path)).length,0);
});
test('existing fixed-destination mappings do not opt into room following',async()=>{
 const f=await fixture();await f.nodes['tag-register'].onclick();f.nodes['tag-id'].value='old-tag';f.nodes['tag-name'].value='Old action';f.nodes['tag-action'].value='call_companion';f.nodes['tag-location'].value='desk';
 await f.nodes['tag-form'].onsubmit({preventDefault(){}});
 assert.equal('room_follow' in JSON.parse(f.calls.find(c=>c.path==='/tags/save').opts.body),false);
});
