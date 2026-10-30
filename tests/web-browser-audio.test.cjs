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
 assert.equal(player.finished,null);assert.ok(player.presenter().envelope.some(v=>v>0));
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
