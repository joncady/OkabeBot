const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function fixture(){
 const nodes={},requests=[];let token='invented-owner',active='default',custom={},hold=false,release;
 function node(){return {value:'',textContent:'',children:[],disabled:false,listeners:{},
  append(x){this.children.push(x);},replaceChildren(...x){this.children=x;},add(x){this.children.push(x);},
  addEventListener(k,fn){this.listeners[k]=fn;},querySelector(){return node();},querySelectorAll(){return [];},focus(){},
  set innerHTML(x){throw Error('Unsafe HTML');}};}
 const get=id=>nodes[id]||=(node());
 const presets=()=>['default','conversation_candidate','native_candidate','custom'].map(id=>({id,label:id,prompts:id==='custom'?custom:{routing:'route '+id,continuation:'reply '+id,preference:'talk '+id}}));
 const context={document:{querySelector:s=>get(s.slice(1)),createElement:node},localStorage:{getItem:()=>null,setItem(){}},
  Option:function(text,value){this.textContent=text;this.value=value;},dashboardAccess:{token:()=>token,remember(){},required(){}},
  fetch:async(path,options)=>{const data=JSON.parse(options.body);requests.push({path,data,options});if(hold)await new Promise(r=>release=r);
   let result={};if(path.endsWith('/treatments')){if(data.selected){active=data.selected;if(data.prompts)custom=data.prompts;}result={selected:active,presets:presets(),receipt:{hash:'1234567890',read_only:active!=='default'}};}
   else if(path.endsWith('/location'))result={locations:[]};else if(path.endsWith('/policy'))result={auto_accept:true,threshold:.9};
   else if(path==='/amadeus/text')result={reply:'Synthetic reply',tools:[],treatment:{id:active}};
   return {ok:true,status:200,json:async()=>result};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/amadeus-text.js','utf8'),context);
 await new Promise(r=>setImmediate(r));
 return{nodes,requests,context,hold(){hold=true;},release(){hold=false;release();},forget(){token='';get('dashboard-forget').listeners.click();}};
}
test('prompt presets load and edits are explicit private saves',async()=>{
 const f=await fixture(),n=f.nodes;n['prompt-treatment-select'].value='native_candidate';n['prompt-treatment-select'].onchange();
 assert.equal(n['prompt-treatment-routing'].value,'route native_candidate');
 n['prompt-treatment-preference'].value='<img src=x> Be concise';n['prompt-treatment-save'].onclick();await new Promise(r=>setImmediate(r));
 const request=f.requests.find(r=>r.data.selected==='custom');assert.equal(request.data.prompts.preference,'<img src=x> Be concise');
 assert.equal(request.options.headers['X-Hardware-Token'],'invented-owner');assert.equal(request.options.cache,'no-store');
 assert.match(n['prompt-treatment-status'].textContent,/read-only tools, no new memories/);
 n['prompt-treatment-default'].onclick();await new Promise(r=>setImmediate(r));assert.ok(f.requests.some(r=>r.data.selected==='default'));
});
test('logout clears private edits and a stale response cannot repopulate them',async()=>{
 const f=await fixture(),n=f.nodes;f.hold();n['prompt-treatment-default'].onclick();await Promise.resolve();f.forget();f.release();await new Promise(r=>setImmediate(r));
 assert.equal(n['prompt-treatment-routing'].value,'');assert.equal(n['prompt-treatment-select'].children.length,0);
 assert.equal(n['amadeus-text-messages'].children.length,0);
 assert.ok(!n['prompt-treatment-status'].textContent.includes('Active:'));
});
