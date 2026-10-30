const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function fixture(){
 const nodes={},calls=[];let token='synthetic-owner';
 const node=()=>({hidden:false,value:'',checked:true,children:[],textContent:'',append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},set innerHTML(v){throw Error('No HTML parsing');}});
 const get=id=>nodes[id]||=(node());get('dashboard-forget').onclick=()=>{token='';};
 let state={mappings:[],locations:[{id:'desk',name:'Example desk'}],learning:false,learned:null};
 const context={document:{getElementById:get,createElement:node},dashboardAccess:{token:()=>token},JSON,Date,URL,setInterval(){},
 fetch:async(path,opts)=>{calls.push({path,opts});const data=opts.body?JSON.parse(opts.body):{};
 if(path==='/tags/learn')state={...state,learning:true,learned:'synthetic-tag'};
 if(path==='/tags/save')state={...state,learning:false,mappings:[{...data,action:'call_companion'}]};
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
