const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const nodes={},events={},node=id=>nodes[id]||={hidden:false,textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;},querySelector(){return node('use');}};
 const context={window:{addEventListener:(name,fn)=>events[name]=fn},localStorage:{getItem(){return null;},setItem(){},removeItem(){}},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})}},document:{querySelector:selector=>node(selector.slice(1)),body:{classList:{toggle(){}}}}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/companion-ui.js','utf8'),context);
 const speaker={enable:async()=>{}};
 const ui=new context.window.CompanionUI(speaker);
 return{ui,nodes,events,speaker};
}
test('audio recovery clears the warning and both visible notice copies',()=>{
 const{ui,nodes}=fixture();
 ui.notice('Reply playback failed: canceled; no automatic replay.','audio');
 assert.equal(nodes.notice.className,'surface-error');
 ui.notice('Playback finished','audio');ui.update({phase:'tv'},false);
 assert.equal(ui.error,'');assert.equal(nodes.notice.textContent,'Playback finished');
 assert.equal(nodes['settings-notice'].textContent,'Playback finished');assert.equal(nodes.notice.className,'sr-only');
 assert.equal(nodes['state-icon'].attrs['data-state'],'ready');
});
test('healthy connectivity never clears an unresolved playback or permission failure',()=>{
 const{ui,nodes}=fixture();
 ui.notice('Speaker disconnected.','audio');ui.notice('Microphone permission denied.','setup');
 ui.notice('Connection unavailable.','connection');ui.clearError('connection');
 assert.match(ui.error,/permission denied/);
 ui.notice('Playback started','audio');assert.match(ui.error,/permission denied/);
 assert.match(nodes['setup-error'].textContent,/permission denied/);
 ui.clearError('setup');ui.update({phase:'tv'},false);assert.equal(ui.error,'');
 assert.equal(nodes['setup-error'].textContent,'');assert.equal(nodes['state-icon'].attrs['data-state'],'ready');
});
test('successful capability retry removes setup denial without hiding another active fault',async()=>{
 const{ui,nodes}=fixture();ui.connected(true);
 ui.notice('Permission denied.','setup');ui.notice('Request rejected.','voice');
 await ui.enable();
 assert.equal(nodes['setup-error'].textContent,'');assert.match(nodes.notice.textContent,/Request rejected/);
 ui.clearError('voice');assert.equal(ui.error,'');assert.equal(nodes['settings-notice'].textContent,'');
});
