const test=require('node:test'),assert=require('node:assert/strict');
const BrowserAudio=require('../okabebot/web/browser-audio.js');
class FakeContext{
 constructor(){this.currentTime=0;this.state='running';this.destination={};this.nodes=[];}
 createGain(){return{gain:{value:1},connect(){}};}
 createBuffer(channels,count,rate){const data=new Float32Array(count);return{length:count,duration:count/rate,getChannelData:()=>data};}
 createBufferSource(){const source={connect(){},start(at){this.at=at;},stop(){this.stopped=true;}};this.nodes.push(source);return source;}
 async resume(){} async close(){}
}
test('PCM is scheduled once in order and completion is acknowledged after buffers end',async()=>{
 global.AudioContext=FakeContext;const calls=[],player=new BrowserAudio(async(path,data)=>{calls.push(data);return{epoch:'one',events:[]};},()=>{});
 await player.enable();player.receive({kind:'start',stream_id:'one'});
 const pcm=Buffer.alloc(4800);for(let i=0;i<2400;i++)pcm.writeInt16LE(2000,i*2);
 player.receive({kind:'chunk',stream_id:'one',pcm_base64:pcm.toString('base64')});player.receive({kind:'end',stream_id:'one'});
 assert.equal(player.finished,null);assert.equal(player.presenter(),null);player.context.currentTime=.05;assert.ok(player.presenter().envelope.some(v=>v>0));
 player.context.nodes.at(-1).onended();assert.equal(player.finished,'one');await player.tick();assert.equal(calls.at(-1).finished,'one');assert.equal(player.presenter(),null);player.close();
});
test('new server epoch cancels old playback and resets cursor without replay',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'new',events:[]}),()=>{});await player.enable();player.epoch='old';player.cursor=99;player.receive({kind:'start',stream_id:'old'});await player.tick();assert.equal(player.cursor,0);assert.equal(player.stream,null);player.close();
});
test('background cache suspend cancels playback and creates a fresh audio session',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'server',events:[]}),()=>{});await player.enable();
 const old=player.session;player.receive({kind:'start',stream_id:'old'});player.cursor=50;player.finished='old';player.suspend();
 assert.notEqual(player.session,old);assert.equal(player.stream,null);assert.equal(player.cursor,0);assert.equal(player.finished,null);player.close();
});
test('late response from a suspended page cannot restart old speech',async()=>{
 global.AudioContext=FakeContext;let release;const player=new BrowserAudio(async()=>({epoch:'server',events:[]}),()=>{});await player.enable();
 player.request=()=>new Promise(resolve=>release=resolve);const pending=player.tick();player.suspend();
 release({epoch:'server',events:[{cursor:1,kind:'start',stream_id:'stale'}]});await pending;assert.equal(player.stream,null);assert.equal(player.cursor,0);player.close();
});
test('speaker recovery replaces a running graph and keeps volume without replay',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'server',events:[]}),()=>{});player.setVolume(37);await player.enable();
 const old=player.context,session=player.session;old.close=async()=>old.closed=true;player.receive({kind:'start',stream_id:'old'});
 await player.restart();assert.equal(old.closed,true);assert.notEqual(player.context,old);assert.notEqual(player.session,session);assert.equal(player.gain.gain.value,.37);assert.equal(player.stream,null);player.close();
});

test('LAN HTTP session generation and suspend do not require randomUUID',()=>{
 const fs=require('node:fs'),vm=require('node:vm');let seed=0;
 const context={Uint8Array,crypto:{getRandomValues:values=>{values.fill(++seed);return values;}},window:{}};
 vm.runInNewContext(fs.readFileSync('okabebot/web/browser-audio.js','utf8'),context);
 const player=new context.window.BrowserAudio(async()=>({events:[]}),()=>{}),first=player.session;
 assert.match(first,/^[a-f0-9]{32}$/);player.cursor=12;player.suspend();
 assert.match(player.session,/^[a-f0-9]{32}$/);assert.notEqual(player.session,first);assert.equal(player.cursor,0);
});

test('TV prebuffer waits for complete PCM then schedules contiguous audio despite arrival stalls',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{},{prebuffer:true});await player.enable();
 player.receive({kind:'start',stream_id:'tv'});const bytes=Buffer.alloc(4800);bytes.writeInt16LE(12000,0);const pcm=bytes.toString('base64');
 player.receive({kind:'chunk',stream_id:'tv',pcm_base64:pcm});player.context.currentTime=3;
 player.receive({kind:'chunk',stream_id:'tv',pcm_base64:pcm});
 assert.equal(player.presenter(),null);assert.equal(player.context.nodes.length,1); // enable sound's silent buffer only
 player.receive({kind:'end',stream_id:'tv'});
 const nodes=player.context.nodes.slice(-1);assert.equal(nodes[0].buffer.duration,.2);assert.ok(nodes[0].at>3);assert.equal(player.context.nodes.length,2);assert.equal(nodes[0].buffer.getChannelData(0)[0],12000/32768);assert.equal(nodes[0].buffer.getChannelData(0)[2400],12000/32768);
 assert.equal(player.finished,null);for(const n of nodes)n.onended();assert.equal(player.finished,'tv');player.close();
});

test('mobile WAV replies use the unlocked gain graph and stop on close',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{});await player.enable();
 player.setVolume(25);player.context.decodeAudioData=async()=>player.context.createBuffer(1,1600,16000);
 await player.playWav(Buffer.from('invented-wav').toString('base64'),[.2,.8]);
 assert.equal(player.gain.gain.value,.25);player.context.currentTime=.05;assert.deepEqual(player.presenter().envelope,[.2,.8]);const node=player.context.nodes.at(-1);player.close();assert.equal(node.stopped,true);
});
test('closing a mobile reply during WAV decode never plays stale audio',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{});await player.enable();
 let release;player.context.decodeAudioData=()=>new Promise(r=>release=r);const context=player.context;
 const pending=player.playWav(Buffer.from('invented-wav').toString('base64'),[]);player.suspend();release(context.createBuffer(1,1600,16000));
 await assert.rejects(pending,/expired/);assert.equal(player.stream,null);assert.equal(context.nodes.length,1);player.close();
});

test('private mobile reply survives unrelated audio hub reconnect failure',async()=>{
 global.AudioContext=FakeContext;let broken=false;
 const player=new BrowserAudio(async()=>{if(broken)throw Error('invented disconnect');return{epoch:'one',events:[]};},()=>{});
 await player.enable();player.context.decodeAudioData=async()=>player.context.createBuffer(1,1600,16000);
 await player.playWav(Buffer.from('invented-wav').toString('base64'),[]);
 const local=player.stream;broken=true;
 const timer=global.setTimeout;global.setTimeout=()=>{};
 try{await player.poll();assert.equal(player.stream,local);assert.equal(local.aborted,false);}finally{global.setTimeout=timer;player.close();}
});

function nativePlayer(){
 const listeners=new Map(),events=[];let stops=0;
 const nativeSink={streamEvent:(event,gain)=>events.push({...JSON.parse(event),gain}),stopStream:()=>stops++};
 const target={addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)};
 const player=new BrowserAudio(async()=>({epoch:'native',events:[]}),()=>{},{nativeSink,eventTarget:target});
 const report=detail=>listeners.get('companion-stream')?.({detail});
 return{player,events,report,stops:()=>stops,listeners};
}
test('native PCM waits for real playback start and drain before acknowledging completion',async()=>{
 const {player,events,report}=nativePlayer();await player.enable();assert.equal(player.context,null);
 const pending=player.waitForStream('native-turn');let ended=false;pending.then(()=>ended=true);
 player.receive({kind:'start',stream_id:'native-turn'});
 player.receive({kind:'chunk',stream_id:'native-turn',sequence:0,pcm_base64:Buffer.alloc(12000).toString('base64')});
 assert.equal(player.presenter(),null);assert.equal(player.finished,null);
 report({kind:'started',stream_id:'native-turn'});assert.equal(player.presenter().activity,'speaking');
 player.receive({kind:'end',stream_id:'native-turn'});await Promise.resolve();assert.equal(ended,false);assert.equal(player.finished,null);
 report({kind:'completed',stream_id:'native-turn'});await pending;assert.equal(player.finished,'native-turn');assert.equal(player.presenter(),null);
 assert.deepEqual(events.map(e=>e.kind),['start','chunk','end']);player.close();
});
test('fast native completion before HTTP reply is remembered and never replayed',async()=>{
 const {player,events,report}=nativePlayer();await player.enable();
 player.receive({kind:'start',stream_id:'fast'});player.receive({kind:'chunk',stream_id:'fast',sequence:0,pcm_base64:Buffer.alloc(2400).toString('base64')});player.receive({kind:'end',stream_id:'fast'});
 report({kind:'completed',stream_id:'fast'});await player.waitForStream('fast');
 player.receive({kind:'start',stream_id:'fast'});assert.equal(events.length,3);player.close();
});
test('native failure and lifecycle cancellation reject the waiting reply without stale completion',async()=>{
 const {player,report,stops,listeners}=nativePlayer();await player.enable();
 player.receive({kind:'start',stream_id:'failed'});const failed=player.waitForStream('failed');report({kind:'failed',stream_id:'failed'});await assert.rejects(failed,/Phone playback failed/);
 await player.enable();player.receive({kind:'start',stream_id:'sleep'});const sleeping=player.waitForStream('sleep');player.suspend();report({kind:'completed',stream_id:'sleep'});await assert.rejects(sleeping,/interrupted/);assert.equal(player.finished,null);assert.ok(stops()>=2);player.close();assert.equal(listeners.size,0);
});
test('streaming browser starts after short jitter buffer before complete generation',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{},{startupBufferMs:200});await player.enable();
 player.receive({kind:'start',stream_id:'incremental'});const pcm=Buffer.alloc(4800).toString('base64');
 player.receive({kind:'chunk',stream_id:'incremental',sequence:0,pcm_base64:pcm});assert.equal(player.context.nodes.length,1);
 player.receive({kind:'chunk',stream_id:'incremental',sequence:1,pcm_base64:pcm});assert.equal(player.context.nodes.length,2);assert.equal(player.stream.ended,false);
 player.context.currentTime=.05;assert.equal(player.presenter().activity,'speaking');
 player.receive({kind:'chunk',stream_id:'incremental',sequence:2,pcm_base64:pcm});assert.equal(player.context.nodes[2].at,player.context.nodes[1].at+.2);player.close();
});
test('duplicate chunks are discarded and missing or malformed PCM aborts the stream visibly',async()=>{
 const {player,events}=nativePlayer();await player.enable();const pcm=Buffer.alloc(2400).toString('base64');
 player.receive({kind:'start',stream_id:'ordered'});player.receive({kind:'chunk',stream_id:'ordered',sequence:0,pcm_base64:pcm});player.receive({kind:'chunk',stream_id:'ordered',sequence:0,pcm_base64:pcm});assert.equal(events.length,2);
 const waiting=player.waitForStream('ordered');player.request=async()=>({epoch:'native',events:[{cursor:1,kind:'chunk',stream_id:'ordered',sequence:2,pcm_base64:pcm}]});await assert.rejects(player.tick(),/Missing audio chunk/);await assert.rejects(waiting,/Missing audio chunk/);assert.equal(player.stream,null);
 assert.equal(player.enabled,false);player.request=async()=>({epoch:'native',events:[]});await player.enable();player.receive({kind:'start',stream_id:'odd'});player.request=async()=>({epoch:'native',events:[{cursor:2,kind:'chunk',stream_id:'odd',pcm_base64:Buffer.alloc(3).toString('base64')}]});await assert.rejects(player.tick(),/Invalid or excessive/);assert.equal(player.stream,null);player.close();
});
test('audio polls never overlap and stale completions after a session change are discarded',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{});await player.enable();
 let release,calls=0;player.request=()=>{calls++;return new Promise(resolve=>release=resolve);};
 const first=player.tick(),second=player.tick();assert.equal(calls,1);player.suspend();release({epoch:'one',events:[{cursor:1,kind:'start',stream_id:'stale'}]});await Promise.all([first,second]);assert.equal(player.stream,null);player.close();
});

test('explicit startup metadata opts a legacy TV sink into bounded buffering',async()=>{
 global.AudioContext=FakeContext;const player=new BrowserAudio(async()=>({epoch:'one',events:[]}),()=>{},{prebuffer:true});await player.enable();
 player.receive({kind:'start',stream_id:'tv-stream',startup_buffer_ms:200});
 player.receive({kind:'chunk',stream_id:'tv-stream',sequence:0,pcm_base64:Buffer.alloc(9600).toString('base64')});
 assert.equal(player.stream.ended,false);assert.equal(player.context.nodes.length,2);assert.equal(player.buffering(),true);
 player.context.currentTime=.05;assert.equal(player.buffering(),false);player.close();
});

test('failed sink sends a disabled-session ACK and polling stays off until explicit enable',async()=>{
 const {player,report}=nativePlayer(),calls=[];player.request=async(path,data)=>{calls.push(data);return{epoch:'native',events:[]};};await player.enable();
 player.receive({kind:'start',stream_id:'ack-failure'});report({kind:'failed',stream_id:'ack-failure'});
 assert.equal(calls.at(-1).enabled,false);assert.equal(player.enabled,false);const count=calls.length;
 await player.tick();assert.equal(calls.length,count);await player.enable();assert.equal(calls.at(-1).enabled,true);player.close();
});
