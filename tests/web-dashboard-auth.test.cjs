const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function auth(hash='',stored=''){
 const nodes={},storage=new Map(stored?[['okabebot-dashboard-access',stored]]:[]),changes=[];
 const context={URL,location:{hash,pathname:'/',search:'',reload(){}},history:{replaceState:(...args)=>changes.push(args)},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},document:{querySelector:id=>nodes[id]||=( {hidden:true,value:'',textContent:''} )},fetch:async()=>({ok:false})};
 vm.createContext(context);vm.runInContext(fs.readFileSync('okabebot/web/dashboard-auth.js','utf8')+'\nglobalThis.access=dashboardAccess;',context);return{...context,nodes,storage,changes};
}
test('setup link stays in memory until authentication succeeds, then clean URL persists access',()=>{
 const s=auth('#'+'a'.repeat(43));assert.equal(s.storage.size,0);s.access.remember();assert.equal(s.storage.get('okabebot-dashboard-access'),'a'.repeat(43));assert.equal(s.changes[0][2],'/');
});
test('stable URL restores browser access and supports local sign-out',()=>{
 const s=auth('','b'.repeat(43));assert.equal(s.access.token(),'b'.repeat(43));s.nodes['#dashboard-forget'].onclick();assert.equal(s.access.token(),'');assert.equal(s.storage.size,0);assert.equal(s.nodes['#dashboard-auth'].hidden,false);
});
test('new browser needs authorization and rejected setup does not persist access',async()=>{
 const s=auth();assert.equal(s.nodes['#dashboard-auth'].hidden,false);s.document.querySelector('#dashboard-access').value='c'.repeat(43);await s.nodes['#dashboard-auth-form'].onsubmit({preventDefault(){}});assert.equal(s.storage.size,0);assert.match(s.nodes['#dashboard-auth-error'].textContent,/not accepted/);
});
test('real dashboard loads authentication before app and includes its controls',()=>{
 const html=fs.readFileSync('okabebot/web/index.html','utf8');
 for(const id of ['dashboard-auth','dashboard-auth-form','dashboard-access','dashboard-auth-error','dashboard-forget'])assert.ok(html.includes('id="'+id+'"'));
 assert.ok(html.indexOf('src="/dashboard-auth.js"')<html.indexOf('src="/app.js"'));
});

test('section fragments never replace saved owner access or disappear on refresh',()=>{
 const s=auth('#amadeus-feeds','b'.repeat(43));assert.equal(s.access.token(),'b'.repeat(43));
 s.access.remember();assert.equal(s.changes.length,0);assert.equal(s.storage.get('okabebot-dashboard-access'),'b'.repeat(43));
 const fresh=auth('#amadeus-feeds');assert.equal(fresh.access.token(),'');assert.equal(fresh.nodes['#dashboard-auth'].hidden,false);
});

test('an invalid setup fragment is reported instead of silently falling back to saved access',()=>{
 const s=auth('#not-a-valid-setup-key','b'.repeat(43));assert.equal(s.access.token(),'');
 assert.equal(s.nodes['#dashboard-auth'].hidden,false);assert.match(s.nodes['#dashboard-auth-error'].textContent,/Invalid setup key/);
 assert.equal(s.storage.get('okabebot-dashboard-access'),'b'.repeat(43));
});
