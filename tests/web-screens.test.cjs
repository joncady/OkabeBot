const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function screen({approved=true,broken=false,microphone=false,denied=false,audioFailure=false,native=false,complete=false,insecureAudio=false}={}){
 let stops=0;
 const calls=[],nodes={},events={};let raf;
 const context2d=new Proxy({},{get:()=>()=>{}});
 const node=id=>nodes[id]||=( {attrs:{},hidden:false,textContent:'',disabled:id==='#mic',value:'',classList:{toggle(){}},getContext:()=>context2d,setAttribute(k,v){this.attrs[k]=v;},querySelector:()=>node('#state-use'),addEventListener(){},setPointerCapture(){}} );
 const storage=new Map(complete?[['companion-setup-complete','1']]:[]);const nativeMessages=[];
 const state={phase:audioFailure?'tv':'preparing',transition_id:'test',duration_seconds:1,tv_side:'left',character:{style:'kurisu'},server_time:1000};
 const context={BrowserAudio:class{async enable(){}async restart(){}setVolume(){}poll(){}presenter(){return null;}suspend(){}stop(){}close(){}},console,Float32Array,Uint8Array,ArrayBuffer,DataView,Date,Math,Error,Promise,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},crypto:{getRandomValues:a=>a.fill(1),randomUUID:()=> 'test-unique-id'},location:{search:''},performance:{now:()=>1000},navigator:microphone?{mediaDevices:{getUserMedia:async()=>{if(denied)throw Error('Permission denied');return{getTracks:()=>[{stop(){stops++;}}]};}}}:{},AudioContext:class{constructor(){throw Error('Audio initialization failed');}},LabRoom:{iso:()=>[0,0],Room:class{constructor(){this.portraits=[1];}setAssets(){if(broken)throw Error('bad artwork');}avatar(){}}},document:{querySelector:node,body:{classList:{toggle(){}}}},window:{...(native?{webkit:{messageHandlers:{companion:{postMessage:message=>nativeMessages.push(message)}}}}:{}),addEventListener:(name,fn)=>events[name]=fn},requestAnimationFrame:fn=>{raf=fn;},setTimeout(){},clearTimeout(){},fetch:async(path,options)=>{calls.push({path,headers:options.headers});return{ok:true,json:async()=>path==='/surfaces/register'?{approved,name:'Phone'}:path==='/surfaces/state'?state:{frames:[[]]}};}};
 if(insecureAudio){delete context.crypto.randomUUID;vm.runInNewContext(fs.readFileSync('okabebot/web/browser-audio.js','utf8'),context);context.BrowserAudio=context.window.BrowserAudio;}
 vm.runInNewContext(fs.readFileSync('okabebot/web/companion-ui.js','utf8'),context);context.CompanionUI=context.window.CompanionUI;
 vm.runInNewContext(fs.readFileSync('okabebot/web/companion.js','utf8'),context);await new Promise(setImmediate);return{calls,nodes,events,raf,storage,nativeMessages,stops:()=>stops};
}
test('unapproved screen discovers itself but never reads scene or sends readiness',async()=>{
 const s=await screen({approved:false});assert.deepEqual(s.calls.map(c=>c.path),['/surfaces/register']);assert.match(s.nodes['#status'].textContent,/Approve/);assert.ok(s.nodes['#mic'].disabled);
 assert.equal(s.storage.get('companion-device').length,64);
});
test('paired screen confirms readiness only after artwork succeeds',async()=>{
 const good=await screen();assert.ok(good.calls.some(c=>c.path==='/surfaces/heartbeat'));
 const bad=await screen({broken:true});assert.ok(!bad.calls.some(c=>c.path==='/surfaces/heartbeat'));
});
test('ordinary HTTP without secure-context microphone is explained and disabled',async()=>{
 const s=await screen();assert.ok(s.nodes['#mic'].disabled);assert.match(s.nodes['#notice'].textContent,/HTTPS/);
 await s.nodes['#pip'].onclick();assert.match(s.nodes['#notice'].textContent,/not available/);
});
test('mobile hold blocks text selection and tap mode avoids hold gesture',async()=>{
 const s=await screen({approved:false});let prevented=0;const e={preventDefault(){prevented++;},pointerId:1};
 s.nodes['#mic'].oncontextmenu(e);s.nodes['#mic'].onselectstart(e);s.nodes['#mic'].onpointerdown(e);assert.ok(prevented>=3);
 s.nodes['#mic-mode'].onclick();assert.equal(s.nodes['#mic'].attrs['aria-label'],'Tap to talk');
 s.nodes['#mic'].onpointerup(e);assert.ok(prevented>=4);
});
test('call companion button summons this screen without supplying another destination',async()=>{
 const s=await screen();await s.nodes['#summon'].onclick();
 const command=s.calls.find(c=>c.path==='/surfaces/summon');assert.ok(command);assert.equal(command.headers['X-Surface-Token'].length,64);
 assert.match(s.nodes['#status'].textContent,/Calling companion/);
});

test('setup confirms capabilities, stops the permission-only mic and disappears',async()=>{
 const s=await screen({microphone:true});
 assert.equal(s.nodes['#setup'].hidden,false);
 await s.nodes['#setup-enable'].onclick();
 assert.equal(s.stops(),1);assert.equal(s.nodes['#setup-finish'].disabled,false);
 assert.ok(!s.calls.some(c=>c.path==='/surfaces/voice'));
 s.nodes['#setup-finish'].onclick();assert.equal(s.nodes['#setup'].hidden,true);
 assert.equal(s.storage.get('companion-setup-complete'),'1');
 s.nodes['#settings'].onclick();assert.equal(s.nodes['#preferences'].hidden,false);
});
test('denied permission remains explicit; view-only is a deliberate choice',async()=>{
 const s=await screen({microphone:true,denied:true});await s.nodes['#setup-enable'].onclick();
 assert.equal(s.nodes['#setup-finish'].disabled,true);assert.match(s.nodes['#setup-error'].textContent,/denied/);
 await s.nodes['#setup-skip'].onclick();assert.equal(s.nodes['#setup-finish'].disabled,false);
 s.nodes['#setup-finish'].onclick();assert.equal(s.nodes['#setup'].hidden,true);
});
test('audio initialization failure releases the acquired recording microphone',async()=>{
 const s=await screen({microphone:true,audioFailure:true});
 s.nodes['#mic-mode'].onclick();await s.nodes['#mic'].onclick({preventDefault(){},detail:0});await new Promise(setImmediate);
 assert.equal(s.stops(),1);assert.ok(!s.calls.some(c=>c.path==='/surfaces/voice'));
});
test('back-forward cache restore registers again and restarts state polling',async()=>{
 const s=await screen();s.events.pagehide({persisted:true});
 s.events.pageshow({persisted:true});await new Promise(setImmediate);
 assert.equal(s.calls.filter(c=>c.path==='/surfaces/register').length,2);
 assert.equal(s.calls.filter(c=>c.path==='/surfaces/state').length,2);
});
test('Mac restores real OS mic permission without capture or setup nag',async()=>{
 const s=await screen({native:true,complete:true,microphone:true});
 assert.ok(s.nativeMessages.includes('permissions'));assert.equal(s.stops(),0);
 s.events['companion-permissions']({detail:{microphone:'granted'}});
 assert.equal(s.nodes['#setup'].hidden,true);assert.equal(s.nodes['#mic-step'].textContent,'Microphone ready');
 s.events['companion-permissions']({detail:{microphone:'denied'}});
 assert.equal(s.nodes['#mic-step'].textContent,'Microphone needs permission');assert.equal(s.stops(),0);
});

test('LAN HTTP with the real audio sink still registers and renders view-only',async()=>{
 const s=await screen({insecureAudio:true});
 assert.ok(s.calls.some(c=>c.path==='/surfaces/register'));
 assert.ok(s.calls.some(c=>c.path==='/surfaces/heartbeat'));
 assert.ok(s.nodes['#mic'].disabled);assert.match(s.nodes['#notice'].textContent,/HTTPS/);
 s.events.pagehide({persisted:true});
});
