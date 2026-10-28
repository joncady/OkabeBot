'use strict';
let locationSignature='',locationDragging=false;
function locationsUI(surface){
 const places=surface.locations||[],signature=JSON.stringify([places,surface.current_location,surface.phase,surface.character_style,surface.scene_world_enabled]);
 if(locationDragging||signature===locationSignature)return;locationSignature=signature;
 const map=document.querySelector('#location-map'),list=document.querySelector('#location-list');map.replaceChildren();list.replaceChildren();
 async function save(id,data){try{await api('/surfaces/layout',{id,...data});locationSignature='';document.querySelector('#location-error').textContent='';}catch(e){document.querySelector('#location-error').textContent=e.message;}}
 if(surface.scene_catalog&&!surface.scene_world_enabled){
  const setup=document.createElement('button');setup.textContent='Set up scene world';
  setup.disabled=surface.phase!=='pi';setup.onclick=async()=>{try{await api('/surfaces/layout',{initialize_scenes:true});locationSignature='';document.querySelector('#location-error').textContent='';}catch(e){document.querySelector('#location-error').textContent=e.message;}};list.append(setup);
 }
 for(const place of places){
  const [x,y]=place.position||[0,0],card=document.createElement('button');card.className='location-pin';card.textContent=place.name+(surface.current_location===place.id?' ●':'');card.style.left=(50+x*10)+'%';card.style.top=(50+y*12)+'%';card.setAttribute('aria-label',`${place.name}, position ${x}, ${y}`);map.append(card);
  let moved=false,start;
  card.onpointerdown=e=>{start=[e.clientX,e.clientY];moved=false;locationDragging=true;card.setPointerCapture(e.pointerId);};
  card.onpointermove=e=>{if(!locationDragging||!start)return;if(Math.hypot(e.clientX-start[0],e.clientY-start[1])>5)moved=true;const r=map.getBoundingClientRect();card.style.left=Math.max(5,Math.min(95,100*(e.clientX-r.left)/r.width))+'%';card.style.top=Math.max(8,Math.min(92,100*(e.clientY-r.top)/r.height))+'%';};
  card.onpointerup=async e=>{if(!start)return;const r=map.getBoundingClientRect();start=null;locationDragging=false;if(moved)await save(place.id,{position:[Math.max(-4,Math.min(4,Math.round((e.clientX-r.left-r.width/2)/(r.width*.1)))),Math.max(-3,Math.min(3,Math.round((e.clientY-r.top-r.height/2)/(r.height*.12))))]});};
  card.onpointercancel=()=>{start=null;locationDragging=false;locationSignature='';};
  const row=document.createElement('div');row.className='location-row';const name=document.createElement('input');name.value=place.name;name.maxLength=40;name.setAttribute('aria-label',`Name for ${place.name}`);row.append(name);
  function button(label,action,disabled=false){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.onclick=action;row.append(b);}
  button('Rename',()=>save(place.id,{name:name.value}));
  const state=document.createElement('span');state.textContent=!place.approved?'Awaiting approval':place.available?'Online':'Offline';row.append(state);
  if(!place.approved)button('Approve screen',()=>save(place.id,{approved:true}));
  else{const missing=surface.scene_world_enabled&&!place.scene_selections?.[surface.character_style];button(missing?'Assign a set':surface.current_location===place.id?'Here':'Move here',()=>action('/surfaces/move',{location_id:place.id}),missing||!place.available||surface.current_location===place.id);if(['browser','mac'].includes(place.adapter))button('Revoke',()=>save(place.id,{approved:false}));}
  if(surface.scene_catalog){
   const mode=document.createElement('select');mode.setAttribute('aria-label',`View for ${place.name}`);
   for(const [id,label] of Object.entries(surface.scene_catalog.presentations)){const o=document.createElement('option');o.value=id;o.textContent=label;o.selected=id===place.presentation;o.disabled=place.adapter==='pi'&&id!=='companion';mode.append(o);}
   mode.onchange=()=>save(place.id,{presentation:mode.value});row.append(mode);
   const character=document.createElement('select');character.setAttribute('aria-label',`Scene character for ${place.name}`);
   for(const style of Object.keys(surface.scene_catalog.characters)){const o=document.createElement('option');o.value=style;o.textContent=style[0].toUpperCase()+style.slice(1);character.append(o);}character.value=surface.character_style;row.append(character);
   const sets=document.createElement('select');sets.disabled=!surface.scene_world_enabled;
   function setOptions(){const style=character.value;sets.replaceChildren();sets.setAttribute('aria-label',`${style} set for ${place.name}`);const empty=document.createElement('option');empty.value='';empty.textContent='Unassigned';empty.disabled=place.adapter==='pi';sets.append(empty);
    for(const id of surface.scene_catalog.characters[style]||[]){const o=document.createElement('option'),owner=places.find(p=>p.id!==place.id&&p.scene_selections?.[style]===id);o.value=id;o.textContent=surface.scene_catalog.sets[id].name+(owner?` · ${owner.name}`:'');o.disabled=Boolean(owner);sets.append(o);}sets.value=place.scene_selections?.[style]||'';
   }character.onchange=setOptions;setOptions();sets.onchange=()=>save(place.id,{scene_selections:{[character.value]:sets.value||null}});row.append(sets);
  }
  const audio=document.createElement('select');audio.setAttribute('aria-label',`Audio destination for ${place.name}`);
  const choices=[['default','Default speaker'],...(['browser','mac'].includes(place.adapter)?[['device','This device / linked speaker']]:[]),['pi','Pi speaker'],['beam','Beam']];
  for(const [id,label] of choices){const option=document.createElement('option');option.value=id;option.textContent=label;option.disabled=id==='beam'&&!surface.beam_audio_available;option.selected=(place.audio_target||'default')===id;audio.append(option);}
  audio.onchange=()=>save(place.id,{audio_target:audio.value});row.append(audio);
  for(const [label,dx,dy] of [['←',-1,0],['→',1,0],['↑',0,-1],['↓',0,1]])button(label,()=>save(place.id,{position:[Math.max(-10,Math.min(10,x+dx)),Math.max(-10,Math.min(10,y+dy))]}));
  if(["browser","mac"].includes(place.adapter))button("Forget",()=>save(place.id,{remove:true}));
  list.append(row);
 }
}
