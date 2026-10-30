const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(initial=[]){
 const nodes={},calls=[];let token='invented-owner',state={items:initial},failSave=false;
 const node=()=>({hidden:false,value:'',checked:true,children:[],textContent:'',listeners:{},disabled:false,append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;},set innerHTML(v){throw Error('No HTML parsing');}});
 const get=id=>nodes[id]||=node();get('dashboard-forget').onclick=()=>{token='';};
 const context={document:{getElementById:get,createElement:node,createTextNode:value=>value},dashboardAccess:{token:()=>token},crypto:require('node:crypto').webcrypto,JSON,Date,window:{confirm:()=>true},fetch:async(path,opts)=>{
  calls.push({path,opts});const body=opts.body?JSON.parse(opts.body):{};
  if(path==='/chores/save'){
   if(failSave)return{ok:false,json:async()=>({error:'Try again'})};
   const item={...body,due_at:2000000};state={items:[...state.items.filter(c=>c.id!==item.id),item],item};
  }
  if(path==='/chores/complete')state={...state,items:state.items.map(c=>c.id===body.id?{...c,due_at:3000000,overdue:false}:c)};
  if(path==='/chores/remove')state={items:state.items.filter(c=>c.id!==body.id)};
  return{ok:true,json:async()=>state};
 }};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/chores.js','utf8')+'\nglobalThis.ui=choresUI;',context);
 return{nodes,calls,context,fail(value){failSave=value;}};
}
test('chores are loaded on demand and default to fortnightly cadence without completing',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);f.nodes['chore-new'].onclick();
 f.nodes['chore-title'].value='Change synthetic towels';f.nodes['chore-delay'].value='2';f.nodes['chore-unit'].value='weeks';f.nodes['chore-repeat'].value='1';
 await f.nodes['chore-form'].onsubmit({preventDefault(){}});
 const value=JSON.parse(f.calls[0].opts.body);assert.equal(value.interval_days,14);assert.equal(value.repeat_days,1);assert.match(value.id,/^[0-9a-f]{32}$/);
 assert.equal(f.calls.some(c=>c.path==='/chores/complete'),false);assert.equal(f.nodes['chores-list'].children[0].children[0].textContent,'Change synthetic towels');
});
test('a failed save retains the draft identity and ignores duplicate submits',async()=>{
 const f=fixture();f.nodes['chore-new'].onclick();f.fail(true);f.nodes['chore-title'].value='Task';f.nodes['chore-delay'].value='1';f.nodes['chore-unit'].value='days';f.nodes['chore-repeat'].value='2';
 const pending=f.nodes['chore-form'].onsubmit({preventDefault(){}});await f.nodes['chore-form'].onsubmit({preventDefault(){}});await pending;
 assert.equal(f.calls.length,1);const id=JSON.parse(f.calls[0].opts.body).id;
 f.fail(false);await f.nodes['chore-form'].onsubmit({preventDefault(){}});assert.equal(JSON.parse(f.calls[1].opts.body).id,id);
});
test('existing chores support explicit completion, pause and configurable snooze without HTML',async()=>{
 const item={id:'a'.repeat(32),title:'<img src=x onerror=1>',enabled:true,interval_days:14,repeat_days:1,due_at:1000,overdue:true},f=fixture([item]);
 await f.context.ui.load();let row=f.nodes['chores-list'].children[0];assert.equal(row.children[0].textContent,item.title);
 await row.children.find(n=>n.textContent==='Mark done').onclick();assert.equal(f.calls.find(c=>c.path==='/chores/complete').opts.headers['X-Hardware-Token'],'invented-owner');
 row=f.nodes['chores-list'].children[0];await row.children.find(n=>n.textContent==='Pause reminders').onclick();const paused=JSON.parse(f.calls.find(c=>c.path==='/chores/save').opts.body);assert.equal(paused.enabled,false);assert.equal(paused.repeat_days,1);
 row=f.nodes['chores-list'].children[0];const label=row.children.find(n=>n.children?.some(v=>v==='Snooze days'));label.children[1].value='5';await row.children.find(n=>n.textContent==='Snooze').onclick();assert.equal(JSON.parse(f.calls.find(c=>c.path==='/chores/snooze').opts.body).days,5);
});
test('forget clears private chore cards and form fields, unchanged polls preserve edited controls',async()=>{
 const item={id:'b'.repeat(32),title:'Private synthetic chore',enabled:true,interval_days:7,repeat_days:1,due_at:1000},f=fixture([item]);await f.context.ui.load();
 const row=f.nodes['chores-list'].children[0];f.context.ui.update([item]);assert.equal(f.nodes['chores-list'].children[0],row);
 await row.children.find(n=>n.textContent==='Edit').onclick();assert.equal(f.nodes['chore-title'].value,item.title);
 f.nodes['dashboard-forget'].onclick();assert.equal(f.nodes['chores-list'].children.length,0);assert.equal(f.nodes['chore-title'].value,'');assert.equal(f.nodes['chore-delay'].value,'2');assert.equal(f.nodes['chore-repeat'].value,'1');
 assert.ok(f.calls.every(c=>!c.path.includes('invented-owner')));
});
