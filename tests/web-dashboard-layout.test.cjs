const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function navigation(hash=''){
 const targets={visible:{tagName:'DETAILS',hidden:false,scrolls:0},private:{tagName:'DETAILS',hidden:true,scrolls:0}},links=[],events={},observers=[];
 for(const [id,target] of Object.entries(targets)){
  target.scrollIntoView=()=>target.scrolls++;
  links.push({getAttribute:()=>`#${id}`,addEventListener(name,fn){this.click=fn;}});
 }
 const context={location:{hash},window:{addEventListener(name,fn){events[name]=fn;}},MutationObserver:class{constructor(fn){this.notify=fn;observers.push(this);}observe(){}},document:{querySelectorAll:()=>links,getElementById:id=>targets[id]}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/dashboard-navigation.js','utf8'),context);
 return{targets,links,events,observers,context};
}
test('navigation reveals details without enabling hidden owner panels or making requests',()=>{
 const f=navigation();f.links[0].click();assert.equal(f.targets.visible.open,true);
 f.links[1].click();assert.equal(f.targets.private.open,undefined);
});
test('a direct known bookmark expands its visible details on initial load',()=>{
 const f=navigation('#visible');assert.equal(f.targets.visible.open,true);assert.equal(f.targets.visible.scrolls,1);
});
test('an owner bookmark waits for authorized unhide and restores only once',()=>{
 const f=navigation('#private');assert.equal(f.targets.private.open,undefined);assert.equal(f.targets.private.scrolls,0);
 f.targets.private.hidden=false;f.observers[0].notify();
 assert.equal(f.targets.private.open,true);assert.equal(f.targets.private.scrolls,1);
 f.observers[0].notify();assert.equal(f.targets.private.scrolls,1);
 f.targets.private.open=false;f.targets.private.hidden=true;f.observers[0].notify();assert.equal(f.targets.private.open,false);
});
test('hash changes restore only known targets and never bypass hidden ancestors',()=>{
 const f=navigation();f.context.location.hash='#unknown';f.events.hashchange();assert.equal(f.targets.visible.open,undefined);
 f.context.location.hash='#visible';f.events.hashchange();assert.equal(f.targets.visible.open,true);
 f.targets.private.hidden=false;f.targets.private.parentElement={hidden:true};f.context.location.hash='#private';f.events.hashchange();assert.equal(f.targets.private.open,undefined);
});
test('setup panels are native collapsed details and essential boundaries stay visible',()=>{
 const html=fs.readFileSync('okabebot/web/amadeus.html','utf8');
 for(const id of ['amadeus-morning','amadeus-feeds','amadeus-habits','amadeus-memory']){
  const tag=html.match(new RegExp(`<details[^>]*id="${id}"[^>]*>`))[0];assert.ok(!/\bopen\b/.test(tag));assert.match(tag,/\bhidden\b/);
 }
 assert.match(html,/<section id="amadeus-controls"/);
 for(const file of ['index.html','amadeus.html']){
  const source=fs.readFileSync(`okabebot/web/${file}`,'utf8'),ids=[...source.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,`${file} duplicate ids`);
  assert.match(source,/src="\/dashboard-navigation.js"/);
 }
});
