const test=require('node:test'),assert=require('node:assert/strict');
const UI=require('../okabebot/web/companion-ui.js');
test('compact card renders title, body and grouped count within its bounds',()=>{
 const text=[],rect=[];const c={save(){},restore(){},fillRect(...r){rect.push(r);},strokeRect(){},measureText:s=>({width:s.length*7}),fillText:(s,x,y)=>text.push([s,x,y])};
 UI.notification(c,{source:'github',title:'Build failed for a deliberately very long repository name',body:'Checks need review before merging this change',member_ids:['a','b','c']});
 assert.equal(text.length,3);assert.ok(text[0][0].endsWith('…'));assert.equal(text[1][0],'×3');assert.match(text[2][0],/Checks/);
 assert.ok(rect.every(([x,y,w,h])=>x>=0&&x+w<=320&&y>=260&&y+h<=320));
});
test('unknown providers use a safe generic glyph and text is never interpreted as markup',()=>{
 const text=[];const c={save(){},restore(){},fillRect(){},strokeRect(){},measureText:s=>({width:s.length*5}),fillText:s=>text.push(s)};
 UI.notification(c,{source:'unknown',title:'<script>',body:'hello\nworld'});assert.deepEqual(text,['<script>','hello world']);
});
