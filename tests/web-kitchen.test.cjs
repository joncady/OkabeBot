const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(overrides={}){
 const nodes={},calls=[];let token='synthetic-owner';
 const create=tag=>({tag,children:[],value:'',textContent:'',checked:false,listeners:{},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},addEventListener(k,fn){this.listeners[k]=fn;},setAttribute(){},set innerHTML(v){throw Error('Untrusted HTML');}});
 const get=id=>nodes[id]||=(create('div'));
 const cfg={enabled:true,proactive:false,allow_eating_out:false,coaching:false,daily_hour:4,expiry_days:3,stale_days:30,planning_days:7,timezone:'UTC',weekdays:['breakfast','dinner'],weekends:['breakfast','lunch','dinner'],tastes:[],avoid:[],goals:[],eating_out_options:[]};
 const state={settings:cfg,imports:[],products:[],recipes:[],plans:[],shopping:[],index:[],browser_jobs:[],browser:{enabled:false,selectors:{}},...overrides};
 const context={document:{getElementById:get,querySelector:s=>get(s.slice(1)),createElement:create},dashboardAccess:{token:()=>token},crypto:require('node:crypto').webcrypto,URL,Blob,confirm:()=>false,fetch:async(path,options)=>{
  calls.push({path,data:options.body&&JSON.parse(options.body),headers:options.headers});
  return {ok:true,status:200,json:async()=>path.startsWith('/kitchen/ingredients')?{items:[{id:'lot',revision:1,name:'<script>synthetic</script>',quantity:2,unit:'can',location:'pantry'}]}:state};
 }};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/kitchen.js','utf8'),context);
 return {nodes,calls,state,async load(){await nodes['kitchen-refresh'].onclick();},forget(){token='';nodes['dashboard-forget'].listeners.click();}};
}
test('kitchen is lazy, source choices are structured, and owner token is a header',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);await f.load();
 assert.ok(f.nodes['kitchen-lots'].children[0].children.some(n=>n.textContent==='<script>synthetic</script>'));
 assert.equal(f.nodes['kitchen-weekdays-breakfast'].checked,true);assert.equal(f.nodes['kitchen-weekdays-lunch'].checked,false);
 f.nodes['kitchen-tastes'].value='vegetarian\nquick';await f.nodes['kitchen-settings'].onsubmit({preventDefault(){}});
 const save=f.calls.find(c=>c.path==='/kitchen/settings');assert.deepEqual(save.data.tastes,['vegetarian','quick']);
 assert.equal(save.headers['X-Hardware-Token'],'synthetic-owner');assert.ok(f.calls.every(c=>!c.path.includes('synthetic-owner')));
});
test('receipt review uses a stable operation ID and ignores concurrent confirms',async()=>{
 const batch={id:'synthetic-receipt',revision:1,source:'fiction',status:'review',items:[{name:'Beans',quantity:2,unit:'can',location:'pantry',confidence:'needs_check'}]};
 const f=fixture({imports:[batch]});await f.load();
 const section=f.nodes['kitchen-imports'].children[0],button=section.children.find(n=>n.tag==='button');
 const pending=button.onclick();await button.onclick();await pending;
 const confirms=f.calls.filter(c=>c.path==='/kitchen/confirm');assert.equal(confirms.length,1);assert.equal(confirms[0].data.items[0].confidence,'confirmed');assert.ok(confirms[0].data.operation_id);
 assert.equal(f.calls.some(c=>c.path==='/kitchen/shopping-approve'),false);
});
test('changed product quantities require saving before a separate approval',async()=>{
 const f=fixture({browser_jobs:[{id:'job',revision:3,name:'Synthetic shopping',status:'review',manifest_hash:'manifest',products:[{product_id:'sku',name:'Beans',price_cents:99,packs:1,requested_name:'beans'}]}]});await f.load();
 const section=f.nodes['kitchen-jobs'].children[0],approval=section.children.find(n=>n.textContent==='Approve exact cart additions (15 minutes)'),row=section.children.find(n=>n.tag==='label'),packs=row.children.find(n=>n.type==='number');
 packs.value=2;packs.oninput();assert.equal(approval.disabled,true);
 await section.children.find(n=>n.textContent==='Save reviewed product choices').onclick();
 const save=f.calls.find(c=>c.path==='/kitchen/shopping-review');assert.equal(save.data.products[0].packs,2);assert.equal(save.data.revision,3);assert.equal(f.calls.some(c=>c.path==='/kitchen/shopping-approve'),false);
});
test('forget clears ingredient cards, pending imports, tastes and NFC ingredient labels',async()=>{
 const f=fixture({products:[{id:'product',name:'Synthetic food'}]});await f.load();assert.equal(f.nodes['kitchen-tag-product'].children.length,1);f.forget();
 assert.equal(f.nodes['kitchen-tag-product'].children.length,0);assert.equal(f.nodes['kitchen-lots'].children.length,0);assert.equal(f.nodes['kitchen-tastes'].value,'');
});
