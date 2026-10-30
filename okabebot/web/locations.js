'use strict';
let locationSignature='',locationDragging=false,arrangedScreen='';
if(typeof window!=='undefined')window.addEventListener('resize',()=>{locationSignature='';});

function screenDirection(a,b){const dx=b[0]-a[0],dy=b[1]-a[1];return Math.abs(dx)>Math.abs(dy)?(dx<0?'left':'right'):(dy<0?'up':'down');}
function screenArrangement(map,places,surface,save){
 if(!places.length)return;
 if(!places.some(p=>p.id===arrangedScreen))arrangedScreen=surface.current_location||places[0].id;
 const selected=places.find(p=>p.id===arrangedScreen)||places[0],cell=[144,112];
 const xs=places.map(p=>p.position[0]),ys=places.map(p=>p.position[1]);
 const bounds=[Math.max(-10,Math.min(...xs)-1),Math.max(-10,Math.min(...ys)-1),Math.min(10,Math.max(...xs)+1),Math.min(10,Math.max(...ys)+1)];
 const width=(bounds[2]-bounds[0]+1)*cell[0],height=(bounds[3]-bounds[1]+1)*cell[1];
 const scale=Math.min(1,(map.clientWidth||864)/width,(map.clientHeight||420)/height);
 const stage=document.createElement('div');stage.className='location-stage';stage.style.width=width+'px';stage.style.height=height+'px';stage.style.transform=`scale(${scale})`;map.append(stage);
 for(const place of places){
  const card=document.createElement('button');card.className='location-screen'+(place.id===selected.id?' selected':'');card.textContent=place.name+(surface.current_location===place.id?' · Here':'');card.dataset.adapter=place.adapter;card.setAttribute('aria-pressed',String(place.id===selected.id));
  card.setAttribute('aria-label',`Arrange ${place.name}, column ${place.position[0]}, row ${place.position[1]}`);
  const center=point=>[(point[0]-bounds[0]+.5)*cell[0],(point[1]-bounds[1]+.5)*cell[1]];
  const paint=point=>{const xy=center(point);card.style.left=xy[0]+'px';card.style.top=xy[1]+'px';};paint(place.position);stage.append(card);
  let start=null,moved=false,point=place.position;
  card.onclick=()=>{if(moved)return;arrangedScreen=place.id;locationSignature='';locationsUI(surface);};
  card.onpointerdown=e=>{start=[e.clientX,e.clientY];point=place.position;moved=false;locationDragging=true;card.setPointerCapture(e.pointerId);};
  card.onpointermove=e=>{if(!start)return;const dx=(e.clientX-start[0])/scale,dy=(e.clientY-start[1])/scale;if(Math.hypot(dx,dy)>5)moved=true;if(!moved)return;
   point=[Math.max(-10,Math.min(10,place.position[0]+Math.round(dx/cell[0]))),Math.max(-10,Math.min(10,place.position[1]+Math.round(dy/cell[1])))];paint(point);
   card.classList.toggle('collision',places.some(p=>p.id!==place.id&&p.position[0]===point[0]&&p.position[1]===point[1]));};
  card.onpointerup=async()=>{if(!start)return;start=null;locationDragging=false;if(!moved)return;
   const occupied=places.some(p=>p.id!==place.id&&p.position[0]===point[0]&&p.position[1]===point[1]);
   if(occupied){document.querySelector('#location-error').textContent='That screen space is occupied. Drop into an empty grid cell.';paint(place.position);card.classList.toggle('collision',false);return;}
   await save(place.id,{position:point});};
  card.onpointercancel=()=>{start=null;locationDragging=false;paint(place.position);card.classList.toggle('collision',false);};
 }
 const controls=document.querySelector('#location-arrangement');controls.replaceChildren();
 const title=document.createElement('strong');title.textContent='Arrange '+selected.name;controls.append(title);
 const side=document.createElement('select');side.setAttribute('aria-label','Placement direction');
 for(const [value,label] of [['left','Left of'],['right','Right of'],['up','Above'],['down','Below']]){const option=document.createElement('option');option.value=value;option.textContent=label;side.append(option);}side.value='left';controls.append(side);
 const anchor=document.createElement('select');anchor.setAttribute('aria-label','Reference screen');for(const place of places.filter(p=>p.id!==selected.id)){const option=document.createElement('option');option.value=place.id;option.textContent=place.name;anchor.append(option);}anchor.value=places.find(p=>p.id!==selected.id)?.id||'';controls.append(anchor);
 const apply=document.createElement('button');apply.textContent='Place screen';apply.disabled=places.length<2;apply.onclick=()=>save(selected.id,{relative_to:anchor.value,placement:side.value});controls.append(apply);
 const hint=document.createElement('span');hint.className='arrangement-hint';
 function explain(){const target=places.find(p=>p.id===anchor.value);if(!target)return;const side=screenDirection(selected.position,target.position);hint.textContent=`From ${selected.name} to ${target.name}: ${side==='up'?'above':side==='down'?'below':side}.`;}
 anchor.onchange=explain;explain();controls.append(hint);
}

function locationsUI(surface){
 const places=surface.locations||[],signature=JSON.stringify([places,surface.current_location,surface.phase,surface.character_style,surface.scene_world_enabled]);
 if(locationDragging||signature===locationSignature)return;locationSignature=signature;
 const map=document.querySelector('#location-map'),list=document.querySelector('#location-list');map.replaceChildren();list.replaceChildren();
 async function save(id,data){try{await api('/surfaces/layout',{id,...data});locationSignature='';document.querySelector('#location-error').textContent='';}catch(e){document.querySelector('#location-error').textContent=e.message;}}
 screenArrangement(map,places,surface,save);
 if(surface.scene_catalog&&!surface.scene_world_enabled){
  const setup=document.createElement('button');setup.textContent='Set up scene world';
  setup.disabled=surface.phase!=='pi';setup.onclick=async()=>{try{await api('/surfaces/layout',{initialize_scenes:true});locationSignature='';document.querySelector('#location-error').textContent='';}catch(e){document.querySelector('#location-error').textContent=e.message;}};list.append(setup);
 }
 for(const place of places){
  const row=document.createElement('div');row.className='location-row';const name=document.createElement('input');name.value=place.name;name.maxLength=40;name.setAttribute('aria-label',`Name for ${place.name}`);row.append(name);
  function button(label,action,disabled=false){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.onclick=action;row.append(b);}
  button('Rename',()=>save(place.id,{name:name.value}));
  const state=document.createElement('span');state.textContent=!place.approved?'Awaiting approval':place.available?'Online':'Offline';row.append(state);
  if(!place.approved)button('Approve screen',()=>save(place.id,{approved:true}));
  else{const missing=surface.scene_world_enabled&&!place.scene_selections?.[surface.character_style];button(missing?'Assign a set':surface.current_location===place.id?'Here':'Move here',()=>action('/surfaces/move',{location_id:place.id}),missing||!place.available||surface.current_location===place.id);if(['browser','mac','alexa'].includes(place.adapter))button('Revoke',()=>save(place.id,{approved:false}));}
  if(surface.scene_catalog){
   const mode=document.createElement('select');mode.setAttribute('aria-label',`View for ${place.name}`);
   for(const [id,label] of Object.entries(surface.scene_catalog.presentations)){const o=document.createElement('option');o.value=id;o.textContent=label;o.selected=id===place.presentation;o.disabled=(place.adapter==='pi'&&id!=='companion')||(place.adapter==='alexa'&&id!=='room');mode.append(o);}
   mode.onchange=()=>save(place.id,{presentation:mode.value});row.append(mode);
   const character=document.createElement('select');character.setAttribute('aria-label',`Scene character for ${place.name}`);
   for(const style of Object.keys(surface.scene_catalog.characters)){const o=document.createElement('option');o.value=style;o.textContent=style[0].toUpperCase()+style.slice(1);character.append(o);}character.value=surface.character_style;row.append(character);
   const sets=document.createElement('select');sets.disabled=!surface.scene_world_enabled;
   function setOptions(){const style=character.value;sets.replaceChildren();sets.setAttribute('aria-label',`${style} set for ${place.name}`);const empty=document.createElement('option');empty.value='';empty.textContent='Unassigned';empty.disabled=place.adapter==='pi';sets.append(empty);
    for(const id of surface.scene_catalog.characters[style]||[]){const o=document.createElement('option'),owner=places.find(p=>p.id!==place.id&&p.scene_selections?.[style]===id);o.value=id;o.textContent=surface.scene_catalog.sets[id].name+(owner?` · ${owner.name}`:'');o.disabled=Boolean(owner)||(place.supported_scenes&&!place.supported_scenes[style]?.includes(id));sets.append(o);}sets.value=place.scene_selections?.[style]||'';
   }character.onchange=setOptions;setOptions();sets.onchange=()=>save(place.id,{scene_selections:{[character.value]:sets.value||null}});row.append(sets);
  }
  const audio=document.createElement('select');audio.setAttribute('aria-label',`Audio destination for ${place.name}`);
  const choices=[['default','Default speaker'],...(['browser','mac','cast'].includes(place.adapter)?[['device','This device / linked speaker']]:[]),['pi','Pi speaker'],['beam','Beam']];
  for(const [id,label] of choices){const option=document.createElement('option');option.value=id;option.textContent=label;option.disabled=id==='beam'&&!surface.beam_audio_available;option.selected=(place.audio_target||'default')===id;audio.append(option);}
  audio.onchange=()=>save(place.id,{audio_target:audio.value});row.append(audio);
  if(place.adapter==='cast'){
    const gain=document.createElement('input');gain.type='range';gain.min=0;gain.max=100;gain.value=place.audio_volume??20;gain.setAttribute('aria-label',`Voice volume for ${place.name}`);
    gain.onchange=()=>save(place.id,{audio_volume:Number(gain.value)});row.append(gain);
  }

  if(["browser","mac","alexa"].includes(place.adapter))button("Forget",()=>save(place.id,{remove:true}));
  list.append(row);
 }
}
