const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
async function fixture(withInventory=false,withTrakt=false,conversationConfig={},householdConfig={},healthConfig={}){
 const nodes={},requests=[];let denied=false,token='synthetic-owner',hold=false,release;
 function node(){return {hidden:false,children:[],value:'',checked:false,textContent:'',
  append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
  setAttribute(key,value){this[key]=value;},reset(){},querySelectorAll(){return [];},
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
  fetch:async(url,options)=>{requests.push({url,options});if(url.endsWith('conversation')&&options.method==='POST')conversationConfig=JSON.parse(options.body);if(url.endsWith('health')&&options.method==='POST')healthConfig=JSON.parse(options.body);if(url.endsWith('household-nudges')&&options.method==='POST')householdConfig=JSON.parse(options.body);if(hold)await new Promise(resolve=>release=resolve);return{status:denied?403:200,ok:!denied,
   json:async()=>url.endsWith('health')?{settings:{enabled:false,daily_steps:0,nudge_after:17,others_detected:false,...healthConfig},privacy:'Private <health>',readings:[{metric:'daily_steps',value:'42',unit:'steps',sample_at:2000000000}]}:url.endsWith('household-nudges')?{config:{enabled:false,...householdConfig},preview:[{text:'<img src=x onerror=alert(1)>'}],state:'source_check_needed'}:url.endsWith('conversation')?{config:{enabled:false,destination:'screen-a',...conversationConfig},destinations:[{id:'screen-a',name:'Synthetic desk'}]}:url.endsWith('trakt-lists')?{state:'connected',items:[{id:'7',title:'Invented watched list'},{id:'8',title:'Another invented list'}],page:1,next_page:null}:url.endsWith('feeds')?{feeds:[withTrakt?{id:'watch_history',label:'Watch history',instructions:'Read only',status:'disabled',fields:[],options:[{key:'history_days',label:'History window (days)',type:'number',min:1,max:365,default:30},{key:'page_budget',label:'Maximum requests per polling cycle',type:'number',min:1,max:20,default:1},{key:'watched_lists',label:'Watched lists',type:'trakt_lists',default:[]}],config:{enabled:false,history_days:30,page_budget:2,watched_lists:['7']}}:{id:'tasks',label:'<img src=x>',instructions:'Read only',status:'disabled',fields:[{key:'entities',label:'To-do lists',domain:'todo'}],config:{enabled:false,entities:[]}}],context:[],connections:withInventory?[{transport:'ha',url:'http://ha.invalid',has_token:true}]:[]}:url.endsWith('ha-inventory')?{rooms:[{id:'study',name:'Study'}],entities:[{id:'todo.invented',name:'Invented list',room:'Study',available:true}],locations:[{id:'screen-a',name:'Desk',area_id:null}]}:url.endsWith('habits')?{config:{enabled:false},preview:{state:'disabled',routines:[],proposals:[]}}:url.endsWith('settings')?{settings:setup,sources:{},coaching_topics:{}}:
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
 assert.equal(f.nodes['amadeus-habits'].hidden,true);assert.equal(f.nodes['habits-preview'].textContent,'');
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

test('routine preview stays owner scoped and enabling it cannot enable delivery',async()=>{
 const f=await fixture();assert.equal(f.nodes['amadeus-habits'].hidden,false);
 f.nodes['habits-enabled'].checked=true;await f.nodes['habits-enabled'].onchange();
 const request=f.requests.find(r=>r.url.endsWith('habits')&&r.options.method==='POST');
 assert.deepEqual(JSON.parse(request.options.body),{enabled:true});
 assert.equal(request.options.headers['X-Hardware-Token'],'synthetic-owner');
 assert.match(f.nodes['habits-state'].textContent,/off|paused/);
});

test('registry feeds render as literal text and are cleared with private access',async()=>{
 const f=await fixture();assert.equal(f.nodes['amadeus-feeds'].hidden,false);
 assert.equal(f.nodes['feed-list'].children[0].children[0].children[0].textContent,'<img src=x>');
 f.nodes['dashboard-forget'].onclick();assert.equal(f.nodes['feed-list'].children.length,0);
 assert.equal(f.nodes['amadeus-feeds'].hidden,true);
});

test('entity rows save arrays and allow individual additions and removals',async()=>{
 const f=await fixture();const card=f.nodes['feed-list'].children[0],form=card.children[2];
 const fieldset=form.children[1],rows=fieldset.children[2],add=fieldset.children[3];
 rows.children[0].children[0].value='todo.invented';add.onclick();
 assert.equal(rows.children.length,2);assert.equal(rows.children[0].children[0].value,'todo.invented');
 rows.children[1].children[0].value='todo.second';rows.children[0].children[1].onclick();
 assert.equal(rows.children.length,1);assert.equal(rows.children[0].children[0].value,'todo.second');
 form.onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
 const post=f.requests.find(r=>r.url.endsWith('feeds')&&r.options.method==='POST');
 assert.deepEqual(JSON.parse(post.options.body),{id:'tasks',config:{enabled:false,entities:['todo.second']}});
});

test('HA inventory is owner-requested and discovery never enables a feed',async()=>{
 const f=await fixture(true);
 assert.ok(!f.requests.some(r=>r.url.endsWith('ha-inventory')));
 const shared=f.nodes['feed-list'].children[0];
 const refresh=shared.children.find(c=>c.textContent==='Refresh rooms and entities');
 await refresh.onclick();
 assert.ok(f.requests.some(r=>r.url.endsWith('ha-inventory')&&r.options.method==='GET'));
 assert.ok(!f.requests.some(r=>r.options.method==='POST'));
 assert.match(f.nodes['feed-list'].children[0].children[4].textContent,/Study/);
 f.nodes['dashboard-forget'].onclick();
 assert.equal(f.nodes['feed-list'].children.length,0);
});

test('Select all discovers choices on demand without a separate refresh or enabling collection',async()=>{
 const f=await fixture(true);
 const card=f.nodes['feed-list'].children[1],form=card.children[2],fieldset=form.children[1];
 const all=fieldset.children[4].children[0],rows=fieldset.children[2];
 assert.notEqual(all.disabled,true);
 await all.onclick();
 assert.equal(rows.children[0].children[0].value,'todo.invented');
 assert.equal(form.children[0].children[0].checked,false);
 assert.ok(!f.requests.some(r=>r.options.method==='POST'));
 assert.notEqual(all.disabled,true);
 fieldset.children[4].children[1].onclick();
 assert.equal(rows.children[0].children[0].value,'');
});

function descendants(node){return [node,...(node.children||[]).flatMap(descendants)];}
test('Trakt list discovery is explicit, keeps saved selection, and adjusts the shared request budget',async()=>{
 const f=await fixture(false,true),card=f.nodes['feed-list'].children[0];
 assert.ok(!f.requests.some(r=>r.url.endsWith('trakt-lists')));
 let nodes=descendants(card),load=nodes.find(n=>n.textContent==='Load my lists');
 assert.ok(nodes.some(n=>n.checked&&n.value==='7'));
 await load.onclick();
 nodes=descendants(card);
 const first=nodes.find(n=>n.type==='checkbox'&&n.value==='7'),second=nodes.find(n=>n.type==='checkbox'&&n.value==='8');
 assert.equal(first.checked,true);assert.equal(second.checked,false);
 assert.ok(!f.requests.some(r=>r.url.endsWith('feeds')&&r.options.method==='POST'));
 second.checked=true;second.onchange();
 const budget=nodes.find(n=>n['aria-label']==='Maximum requests per polling cycle');
 assert.equal(budget.min,3);assert.equal(budget.value,3);
 const form=card.children.find(n=>n.onsubmit);form.onsubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 const post=f.requests.find(r=>r.url.endsWith('feeds')&&r.options.method==='POST');
 assert.deepEqual(JSON.parse(post.options.body),{id:'watch_history',config:{enabled:false,history_days:30,page_budget:3,watched_lists:['7','8']}});
});


test('proactive cadence defaults preserve legacy limits and owner can edit without changing destination',async()=>{
 const f=await fixture();assert.equal(f.nodes['conversation-max-per-day'].value,1);assert.equal(f.nodes['conversation-min-gap'].value,120);
 f.nodes['conversation-enabled'].checked=true;f.nodes['conversation-max-per-day'].value='3';f.nodes['conversation-min-gap'].value='150';
 f.nodes['conversation-form'].onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
 const request=f.requests.find(r=>r.url.endsWith('conversation')&&r.options.method==='POST');
 assert.deepEqual(JSON.parse(request.options.body),{enabled:true,destination:'screen-a',max_per_day:3,min_gap_minutes:150});
 assert.equal(f.nodes['conversation-max-per-day'].value,3);assert.equal(f.nodes['conversation-min-gap'].value,150);
});

test('configured proactive cadence is shown and private form resets on owner logout',async()=>{
 const f=await fixture(false,false,{enabled:true,destination:'screen-a',max_per_day:5,min_gap_minutes:240});
 assert.equal(f.nodes['conversation-max-per-day'].value,5);assert.equal(f.nodes['conversation-min-gap'].value,240);
 f.nodes['dashboard-forget'].onclick();assert.equal(f.nodes['amadeus-controls'].hidden,true);
 assert.equal(f.nodes['conversation-destination'].children.length,0);
});


test('household controls use typed complete configuration without changing device or coaching permissions',async()=>{
 const f=await fixture();
 assert.equal(f.nodes['household-enabled'].checked,false);
 assert.equal(f.nodes['household-departure-away-minutes'].value,10);
 assert.equal(f.nodes['household-comfort-hold-minutes'].value,15);
 f.nodes['household-enabled'].checked=true;
 f.nodes['household-departure-enabled'].checked=false;
 f.nodes['household-departure-away-minutes'].value='25';
 f.nodes['household-bedtime-start'].value='20:30';
 f.nodes['household-bedtime-end'].value='23:30';
 f.nodes['household-cold-c'].value='62.6';
 f.nodes['household-hot-c'].value='82.4';
 f.nodes['household-cooldown-hours'].value='24';
 f.nodes['household-form'].onsubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 const posts=f.requests.filter(r=>r.options.method==='POST');
 assert.equal(posts.length,1);
 assert.ok(posts[0].url.endsWith('household-nudges'));
 assert.deepEqual(JSON.parse(posts[0].options.body),{
  enabled:true,departure_enabled:false,departure_away_minutes:25,bedtime_enabled:true,
  bedtime_start:'20:30',bedtime_end:'23:30',comfort_enabled:true,cold_c:17,hot_c:28,
  comfort_hold_minutes:15,cooldown_hours:24
 });
 assert.equal(posts[0].options.headers['X-Hardware-Token'],'synthetic-owner');
 assert.equal(f.nodes['household-departure-away-minutes'].value,25);
 assert.equal(f.nodes['household-cooldown-hours'].value,24);
});

test('household preview is literal private content and explicit refresh never saves',async()=>{
 const f=await fixture(false,false,{}, {enabled:true,bedtime_enabled:false,comfort_enabled:false});
 assert.equal(f.nodes['household-enabled'].checked,true);
 assert.equal(f.nodes['household-cold-c'].value,64.4);
 assert.equal(f.nodes['household-hot-c'].value,80.6);
 assert.equal(f.nodes['household-bedtime-enabled'].checked,false);
 assert.equal(f.nodes['household-comfort-enabled'].checked,false);
 assert.match(f.nodes['household-preview'].textContent,/<img src=x/);
 await f.nodes['household-refresh'].onclick();
 assert.ok(!f.requests.some(r=>r.options.method==='POST'));
 f.nodes['dashboard-forget'].onclick();
 assert.equal(f.nodes['household-preview'].textContent,'');
 assert.equal(f.nodes['household-state'].textContent,'');
 assert.equal(f.nodes['amadeus-controls'].hidden,true);
});

test('household HTML exposes bounded thresholds and retains attention/identity caveats',()=>{
 const html=fs.readFileSync('okabebot/web/amadeus.html','utf8');
 assert.match(html,/household-departure-away-minutes[^>]+min="1"[^>]+max="120"/);
 assert.match(html,/household-cold-c[^>]+min="41"[^>]+max="77"/);
 assert.match(html,/household-hot-c[^>]+min="68"[^>]+max="104"/);
 assert.match(html,/household-cooldown-hours[^>]+min="1"[^>]+max="72"/);
 assert.match(html,/Device activity does not identify anyone or prove occupancy/);
 assert.match(html,/separate from optional health-habit coaching/);
 assert.match(html,/Spoken reminders share the proactive daily limit/);
});

test('private health controls save explicit goals and shared-room suppression without enabling feed',async()=>{
 const f=await fixture();
 assert.equal(f.nodes['health-enabled'].checked,false);
 assert.equal(f.nodes['health-state'].textContent,'Private <health>');
 assert.match(f.nodes['health-readings'].children[0].textContent,/daily steps: 42/);
 f.nodes['health-enabled'].checked=true;f.nodes['health-daily-steps'].value='4321';
 f.nodes['health-nudge-after'].value='18';f.nodes['health-others-detected'].checked=true;
 f.nodes['health-form'].onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
 const saved=f.requests.find(r=>r.url.endsWith('/health')&&r.options.method==='POST');
 assert.deepEqual(JSON.parse(saved.options.body),{enabled:true,daily_steps:4321,nudge_after:18,others_detected:true});
 assert.ok(!f.requests.some(r=>r.url.endsWith('/feeds')&&r.options.method==='POST'));
 f.deny();await assert.rejects(()=>f.context.ui.load());assert.equal(f.nodes['health-readings'].children.length,0);
});
