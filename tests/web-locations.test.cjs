const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const catalog=require('../okabebot/assets/scene-sets.json');
function dashboard(enabled){
 const calls=[],nodes={};
 function element(tag){return{tag,children:[],style:{},dataset:{},classList:{toggle(){}},append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},setAttribute(key,value){this[key]=value;}};}
 const context={document:{createElement:element,querySelector:selector=>nodes[selector]||=(element('div'))},api:async(path,data)=>calls.push({path,data}),action(){}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/locations.js','utf8'),context);
 const state={phase:'pi',current_location:'home',character_style:'okabe',scene_world_enabled:enabled,scene_catalog:catalog,locations:[{id:'home',name:'Home',adapter:'pi',approved:true,available:true,presentation:'companion',position:[0,0],scene_selections:enabled?{okabe:'pixel-lab'}:{}},{id:'tv',name:'TV',adapter:'cast',approved:true,available:true,presentation:'room',position:[-1,0],scene_selections:enabled?{okabe:'maid-cafe'}:{}}]};
 context.locationsUI(state);return{calls,nodes,state,context};
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
