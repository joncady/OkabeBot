const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const catalog=require('../okabebot/assets/scene-sets.json');
function dashboard(enabled){
 const calls=[],nodes={},events={};
 function element(tag){return{tag,children:[],style:{},dataset:{},classList:{toggle(){}},append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},setAttribute(key,value){this[key]=value;}};}
 const context={window:{addEventListener(name,handler){events[name]=handler;}},document:{createElement:element,querySelector:selector=>nodes[selector]||=(element('div'))},api:async(path,data)=>calls.push({path,data}),action(){}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/locations.js','utf8'),context);
 const state={phase:'pi',current_location:'home',character_style:'okabe',scene_world_enabled:enabled,scene_catalog:catalog,locations:[{id:'home',name:'Home',adapter:'pi',approved:true,available:true,presentation:'companion',position:[0,0],scene_selections:enabled?{okabe:'pixel-lab'}:{}},{id:'tv',name:'TV',adapter:'cast',approved:true,available:true,presentation:'room',position:[-1,0],scene_selections:enabled?{okabe:'maid-cafe'}:{}}]};
 context.locationsUI(state);return{calls,nodes,state,context,events};
}
test('scene setup is explicit and sends one initialization transaction',async()=>{
 const d=dashboard(false),children=d.nodes['#location-list'].children,setup=children[0];
 assert.equal(setup.textContent,'Set up scene world');
 const set=children[1].children.find(n=>n['aria-label']==='okabe set for Home');assert.equal(set.disabled,true);
 await setup.onclick();assert.equal(d.calls.length,1);assert.equal(d.calls[0].path,'/surfaces/layout');
 assert.deepEqual(JSON.parse(JSON.stringify(d.calls[0].data)),{initialize_scenes:true});
});
test('occupied sets cannot be selected on another screen and home cannot be unassigned',()=>{
 const d=dashboard(true),[home,tv]=d.nodes['#location-list'].children;
 const homeSets=home.children.find(n=>n['aria-label']==='okabe set for Home');
 assert.equal(homeSets.children[0].disabled,true);
 assert.equal(homeSets.children.find(n=>n.value==='maid-cafe').disabled,true);
 const tvSets=tv.children.find(n=>n['aria-label']==='okabe set for TV');
 assert.equal(tvSets.children.find(n=>n.value==='pixel-lab').disabled,true);
 assert.match(tvSets.children.find(n=>n.value==='pixel-lab').textContent,/Home/);
});
test('relative placement uses selected screen and explicit reference, without arrow buttons',async()=>{
 const d=dashboard(true),controls=d.nodes['#location-arrangement'].children;
 controls.find(n=>n['aria-label']==='Placement direction').value='up';
 controls.find(n=>n['aria-label']==='Reference screen').value='tv';
 await controls.find(n=>n.textContent==='Place screen').onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(d.calls[0].data)),{id:'home',relative_to:'tv',placement:'up'});
 assert.match(controls.find(n=>n.className==='arrangement-hint').textContent,/From Home to TV: left/);
});
test('drag snaps to grid and rejects occupied screen space',async()=>{
 const d=dashboard(true),stage=d.nodes['#location-map'].children[0],home=stage.children[0];
 home.setPointerCapture=()=>{};
 home.onpointerdown({clientX:0,clientY:0,pointerId:1});home.onpointermove({clientX:-144,clientY:0});await home.onpointerup();
 assert.equal(d.calls.length,0);assert.match(d.nodes['#location-error'].textContent,/occupied/);
 home.onpointerdown({clientX:0,clientY:0,pointerId:2});home.onpointermove({clientX:150,clientY:115});await home.onpointerup();
 assert.deepEqual(JSON.parse(JSON.stringify(d.calls[0].data)),{id:'home',position:[1,1]});
});

test('viewport resize refits screen arrangement on the next state update',()=>{
 const d=dashboard(true),map=d.nodes['#location-map'];
 const first=map.children[0];
 map.clientWidth=240;map.clientHeight=160;d.events.resize();d.context.locationsUI(d.state);
 assert.notEqual(map.children[0],first);
 const scale=Number(map.children[0].style.transform.match(/scale\((.*)\)/)[1]);
 assert.ok(scale<1);
 assert.ok(parseFloat(map.children[0].style.width)*scale<=240);
 assert.ok(parseFloat(map.children[0].style.height)*scale<=160);
});
test('Alexa screens expose only their artwork and Room presentation, with revoke controls',()=>{
 const d=dashboard(true);d.state.locations[1].scene_selections={};
 d.state.locations.push({id:'echo',name:'Study Echo',adapter:'alexa',approved:true,available:true,position:[1,0],presentation:'room',scene_selections:{},supported_scenes:{okabe:['maid-cafe']}});
 d.context.locationsUI(d.state);
 const row=d.nodes['#location-list'].children[2],view=row.children.find(n=>n['aria-label']==='View for Study Echo');
 assert.equal(view.children.find(n=>n.value==='companion').disabled,true);
 const sets=row.children.find(n=>n['aria-label']==='okabe set for Study Echo');
 assert.equal(sets.children.find(n=>n.value==='maid-cafe').disabled,false);
 const character=row.children.find(n=>n['aria-label']==='Scene character for Study Echo');character.value='kurisu';character.onchange();
 assert.ok(sets.children.filter(n=>n.value).every(n=>n.disabled));
 assert.ok(row.children.some(n=>n.textContent==='Revoke'));
 assert.ok(row.children.some(n=>n.textContent==='Forget'));
 const audio=row.children.find(n=>n['aria-label']==='Audio destination for Study Echo');
 assert.ok(audio.children.every(n=>n.value!=='device'));
});
