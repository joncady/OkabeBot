const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const nodes={},calls=[];let token='invented-owner',hold=false,releases=[];
 function node(){return {value:'',children:[],listeners:{},append(...x){this.children.push(...x);},replaceChildren(...x){this.children=x;},addEventListener(k,fn){this.listeners[k]=fn;},querySelector(){return node();},set innerHTML(_){throw Error('Unsafe HTML');}};}
 const get=id=>nodes[id]||=node();
 const context={document:{querySelector:s=>get(s.slice(1)),createElement:node},setInterval(){},dashboardAccess:{token:()=>token,remember(){},required(){}},fetch:async(path,options)=>{
  calls.push({path,options});if(hold)await new Promise(r=>releases.push(r));
  return {ok:true,status:200,json:async()=>path==='/preparations'?{jobs:[{id:'a'.repeat(32),revision:2,title:'<img src=x>',status:'awaiting_review',items:['Tea'] }]}:{enabled:true,reduced_motion:false}};
 }};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/preparations.js','utf8'),context);
 get('preparation-items');
 return {nodes,calls,hold(){hold=true;},release(){hold=false;releases.splice(0).forEach(r=>r());},forget(){token='';get('dashboard-forget').listeners.click();}};
}
const flush=()=>new Promise(setImmediate);
test('drafts load on disclosure and review sends exact revision without interpreting content',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);const n=f.nodes;n['preparation-panel'].open=true;n['preparation-panel'].listeners.toggle();await flush();
 const card=n['preparation-list'].children[0];assert.equal(card.children[0].textContent,'<img src=x>');await card.children[3].onclick();
 const write=f.calls.find(c=>c.path==='/preparations/update');assert.deepEqual(JSON.parse(write.options.body),{action:'save',id:'a'.repeat(32),revision:2});
 assert.equal(write.options.headers['X-Hardware-Token'],'invented-owner');
});
test('forget clears drafts and input, and stale reads cannot restore private content',async()=>{
 const f=fixture(),n=f.nodes;n['preparation-panel'].open=true;n['preparation-panel'].listeners.toggle();await flush();assert.equal(n['preparation-list'].children.length,1);
 n['preparation-items'].value='Invented private groceries';f.hold();n['preparation-refresh'].onclick();await Promise.resolve();f.forget();f.release();await flush();
 assert.equal(n['preparation-items'].value,'');assert.equal(n['preparation-list'].children.length,0);
});
