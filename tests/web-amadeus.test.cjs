const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
async function fixture(){
 const nodes={},requests=[];let denied=false,token='synthetic-owner',hold=false,release;
 function node(){return {hidden:false,children:[],value:'',checked:false,textContent:'',
  append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
  setAttribute(){},reset(){},querySelectorAll(){return [];},
  set innerHTML(value){throw Error('Private content must never be parsed as HTML');}};}
 const get=id=>nodes[id]||=(node());
 const radios=['choose_topics','not_now','no'].map(value=>Object.assign(node(),{value,checked:value==='not_now'}));
 const document={getElementById:get,createElement:node,createTextNode:text=>({textContent:text}),
  querySelectorAll:()=>radios,querySelector(selector){
   if(selector.includes(':checked'))return radios.find(r=>r.checked);
   const value=selector.match(/value="([^"]+)"/)[1];return radios.find(r=>r.value===value);
  }};
 get('dashboard-forget').onclick=()=>{token='';};
 const setup={profile:'synthetic-profile',sources:[],retention_days:30,timezone:'UTC',
  quiet_start:'22:00',quiet_end:'08:00',coaching_choice:'not_now',coaching_mode:'establish',paused:true,guest:false};
 const context={document,Intl,Date,JSON,URL,Blob,setTimeout,
  dashboardAccess:{token:()=>token,remember(){},required(){get('dashboard-auth').hidden=false;}},
  fetch:async(url,options)=>{requests.push({url,options});if(hold)await new Promise(resolve=>release=resolve);return{status:denied?403:200,ok:!denied,
   json:async()=>url.endsWith('settings')?{settings:setup,sources:{},coaching_topics:{}}:
   {events:[],preferences:[{key:'user.test',value:'<img src=x onerror=alert(1)>'}]}};}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('okabebot/web/amadeus.js','utf8')+'\nglobalThis.ui=amadeusUI;',context);
 await new Promise(resolve=>setImmediate(resolve));
 return{nodes,requests,context,deny(){denied=true;},hold(){hold=true;},release(){hold=false;release();}};
}
test('saved permissions collapse and private values render as text under owner authority',async()=>{
 const f=await fixture();assert.equal(f.nodes['amadeus-setup'].hidden,true);
 assert.equal(f.nodes['amadeus-review'].hidden,false);
 const item=f.nodes['memory-list'].children[0].children[0];
 assert.match(item.textContent,/<img src=x/);
 assert.ok(f.requests.every(r=>r.options.headers['X-Hardware-Token']==='synthetic-owner'));
 assert.ok(f.requests.every(r=>!r.url.includes('synthetic-owner')));
});
test('forget browser access removes rendered private records and hides controls',async()=>{
 const f=await fixture();f.nodes['dashboard-forget'].onclick();
 assert.equal(f.nodes['amadeus-memory'].hidden,true);assert.equal(f.nodes['amadeus-controls'].hidden,true);
 assert.equal(f.nodes['memory-list'].children.length,0);assert.equal(f.nodes['event-list'].textContent,'');
});
test('revoked owner access clears previously visible records',async()=>{
 const f=await fixture();f.deny();await assert.rejects(f.context.ui.load());
 assert.equal(f.nodes['amadeus-memory'].hidden,true);assert.equal(f.nodes['memory-list'].children.length,0);
 assert.equal(f.nodes['dashboard-auth'].hidden,false);
});
test('an in-flight response cannot repaint private records after local logout',async()=>{
 const f=await fixture();f.hold();const loading=f.context.ui.load();
 f.nodes['dashboard-forget'].onclick();f.release();await assert.rejects(loading);
 assert.equal(f.nodes['amadeus-memory'].hidden,true);assert.equal(f.nodes['memory-list'].children.length,0);
});
