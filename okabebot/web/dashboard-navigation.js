'use strict';
// Native fragments remain bookmarkable; opening a section never changes saved choices.
(()=>{
 const targets=new Map();let restored='';
 function ancestors(target){const result=[];for(let node=target;node;node=node.parentElement)result.push(node);return result;}
 function reveal(id,restore=false){
  const target=targets.get(id);if(!target)return false;
  const chain=ancestors(target);if(chain.some(node=>node.hidden))return false;
  for(const node of chain)if(node.tagName==='DETAILS')node.open=true;
  if(restore&&restored!==id){target.scrollIntoView({block:'start'});restored=id;}
  return true;
 }
 function restoreFragment(){reveal(location.hash.slice(1),true);}
 for(const link of document.querySelectorAll('nav.dashboard-nav a[href^="#"]')){
  const id=link.getAttribute('href').slice(1),target=document.getElementById(id);if(!target)continue;
  targets.set(id,target);link.addEventListener('click',()=>reveal(id));
 }
 window.addEventListener('hashchange',()=>{restored='';restoreFragment();});
 // Owner panels become visible only after their existing authorized load succeeds.
 // Observe visibility only; never read, fetch, or unhide private content ourselves.
 const observer=new MutationObserver(restoreFragment),observed=new Set();
 for(const target of targets.values())for(const node of ancestors(target)){
  if(observed.has(node))continue;observed.add(node);observer.observe(node,{attributes:true,attributeFilter:['hidden']});
 }
 restoreFragment();
})();
