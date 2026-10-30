const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(preview=[]){
 const nodes={},requests=[],listeners={},timers=[];let token='synthetic-owner',denied=false,hold=false,release,observe;
 const node=()=>({hidden:true,children:[],textContent:'',listeners:{},replaceChildren(...v){this.children=v;},append(...v){this.children.push(...v);},addEventListener(k,fn){this.listeners[k]=fn;},set innerHTML(_){throw Error('No HTML parsing');}});
 const get=id=>nodes[id]||=node(),link=node();get('dashboard-forget').onclick=()=>{token='';};
 const document={hidden:false,getElementById:get,createElement:node,querySelectorAll:()=>[link],addEventListener(k,fn){listeners[k]=fn;}};
 const context={document,window:{addEventListener(k,fn){listeners[k]=fn;}},location:{hash:''},setInterval(fn,ms){timers.push({fn,ms});},IntersectionObserver:class{constructor(fn){observe=fn;}observe(){}},dashboardAccess:{token:()=>token,required(){}},fetch:async(url,options)=>{requests.push({url,options});if(hold)await new Promise(resolve=>release=resolve);return {ok:!denied,status:denied?403:200,json:async()=>({preview})};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/household-nudges.js','utf8')+'\nglobalThis.ui=householdNotesUI;',context);
 return{nodes,requests,timers,context,link,observe:value=>observe([{isIntersecting:value}]),deny(){denied=true;},hold(){hold=true;},release(){hold=false;release();},preview(value){preview=value;}};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('notes stay hidden until Today opens; literal candidates use owner-only reads',async()=>{
 const f=fixture([{text:'<img src=x onerror=1>',delivery:'dashboard_only'}]);
 assert.equal(f.requests.length,0);f.link.listeners.click();await flush();
 assert.equal(f.nodes['household-notes-panel'].hidden,false);
 assert.equal(f.nodes['household-notes-list'].children[0].textContent,'<img src=x onerror=1>');
 assert.equal(f.requests[0].options.method,'GET');assert.equal(f.requests[0].options.headers['X-Hardware-Token'],'synthetic-owner');
 assert.ok(!f.requests[0].url.includes('synthetic-owner'));
 f.preview([]);await f.context.ui.load();assert.equal(f.nodes['household-notes-panel'].hidden,true);
});
test('visible Today polls at 60 seconds, inactive/background view does not fetch',async()=>{
 const f=fixture([{text:'Imaginary note'}]);assert.equal(f.timers[0].ms,60000);
 f.timers[0].fn();await flush();assert.equal(f.requests.length,0);
 f.observe(true);await flush();assert.equal(f.requests.length,1);
 f.timers[0].fn();await flush();assert.equal(f.requests.length,2);
 f.context.document.hidden=true;f.timers[0].fn();await flush();assert.equal(f.requests.length,2);
 f.context.document.hidden=false;f.observe(false);f.timers[0].fn();await flush();assert.equal(f.requests.length,2);
});
test('revocation and local forget immediately erase notes and block stale responses',async()=>{
 const f=fixture([{text:'Private invented note'}]);await f.context.ui.load();f.deny();await f.context.ui.load();
 assert.equal(f.nodes['household-notes-panel'].hidden,true);assert.equal(f.nodes['household-notes-list'].children.length,0);
 const g=fixture([{text:'Old private note'}]);g.hold();const pending=g.context.ui.load();g.context.dashboardAccess.required();g.release();await pending;
 assert.equal(g.nodes['household-notes-panel'].hidden,true);assert.equal(g.nodes['household-notes-list'].children.length,0);
 const h=fixture([{text:'Private note'}]);await h.context.ui.load();h.nodes['dashboard-forget'].onclick();
 assert.equal(h.nodes['household-notes-list'].children.length,0);await h.context.ui.load();assert.equal(h.requests.length,1);
});
