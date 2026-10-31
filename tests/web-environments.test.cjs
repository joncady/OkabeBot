const test=require('node:test'),assert=require('node:assert/strict');
const environments=require('../okabebot/web/character-environments.js');
const {Room,iso,anchors}=require('../okabebot/web/lab-room.js');
function canvas(){const rectangles=[],texts=[];const object={fillRect(...xy){rectangles.push(xy);},fillText(text){texts.push(text);},measureText:text=>({width:text.length*8})};return{c:new Proxy(object,{get:(target,key)=>target[key]||(()=>{})}),rectangles,texts};}
test('character scenery does not change the other characters default lab',()=>{
 assert.equal(environments.theme({style:'sonic'}),'green-hill');
 for(const style of ['kurisu','okabe','pip','custom'])assert.equal(environments.theme({style}),'pixel-lab');
});
test('compact Green Hill leaves the background transparent',()=>{
 const {c,rectangles}=canvas();environments.compact(c,1000);
 assert.ok(rectangles.length>10);assert.ok(!rectangles.some(([x,y,w,h])=>x<=0&&y<=0&&w>=320&&h>=320));
});
test('outdoor sign keeps live notifications and the same movement anchors',()=>{
 const {c,texts}=canvas(),room=new Room();const before=anchors.door.slice();
 environments.room(c,{state:{notification:{title:'Build passed',body:'Ready to review'}},now:1000,visible:false},room,iso,anchors.door);
 assert.ok(texts.includes('Build passed'));assert.ok(texts.includes('Ready to review'));assert.deepEqual(anchors.door,before);
});

test('every catalog set supports both presentations and unassigned screens stay empty',()=>{
 global.document={createElement:()=>({getContext:()=>canvas().c})};
 const catalog=require('../scripts/character-catalog.cjs').scenes;
 for(const [style,sets] of Object.entries(catalog.characters))for(const set of sets){
  const {c,rectangles}=canvas();
  environments.compact(c,1000,1,set);assert.ok(rectangles.length>0);
  assert.equal(environments.theme({style},{set}),set);
  new Room().render(c,{state:{character:{style},environment:{set,assigned:true,presentation:'room',name:catalog.sets[set].name}},now:1000,visible:false,opacity:1});
 }
 const {c,rectangles}=canvas();new Room().render(c,{state:{environment:{assigned:false}},now:1000});
 assert.equal(rectangles.length,0);
});
