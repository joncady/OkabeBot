package dev.okabebot.amadeus;

import java.util.ArrayDeque;
import java.util.LinkedHashSet;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** Bounded, ordered PCM delivery. Completion means the sink consumed the last frame. */
final class PcmStreamEngine implements AutoCloseable {
    static final int SAMPLE_RATE=24000, MAX_BYTES=1440000, MAX_CHUNK=240000, PREBUFFER_BYTES=11520;
    interface Sink extends AutoCloseable {
        void open(double gain) throws Exception;
        void write(byte[] pcm) throws Exception;
        long playedFrames();
        int underruns();
        void gain(double gain);
        default void finishInput() throws Exception {}
        void abort();
        void close();
    }
    interface Factory { Sink create(); }
    interface Events { void accept(String kind,String id,int underruns); }
    final Factory factory;
    final Events events;
    final ExecutorService writer=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(1),new ThreadPoolExecutor.DiscardOldestPolicy());
    final Object guard=new Object();
    State active;
    final LinkedHashSet<String> retired=new LinkedHashSet<>();
    boolean closed;
    static final class State {
        final String id;
        volatile double gain;
        final ArrayDeque<byte[]> queue=new ArrayDeque<>();
        long cursor,total,written,lastInput=System.nanoTime();
        int queued;
        boolean ended,started,terminal,reportedTerminal;
        volatile boolean cancelled;
        final int prebufferBytes;
        volatile Sink sink;
        State(String id,long cursor,double gain,int startupMs){this.id=id;this.cursor=cursor;this.gain=gain;this.prebufferBytes=startupMs*48;}
    }
    PcmStreamEngine(Factory factory,Events events){this.factory=factory;this.events=events;}
    void start(String id,long cursor,double gain){start(id,cursor,gain,240);}
    void start(String id,long cursor,double gain,int startupMs){
        if(startupMs<100 || startupMs>2000 || id==null || !id.matches("[A-Za-z0-9_-]{1,96}") || cursor<0 || !Double.isFinite(gain))throw new IllegalArgumentException("Invalid stream start");
        State prior;
        State next;
        synchronized(guard){
            if(closed)throw new IllegalStateException("Player closed");
            if(retired.contains(id))return;
            if(active!=null && active.id.equals(id))return; // Repeated relay start is not replayed.
            prior=active;
            next=new State(id,cursor,Math.max(0,Math.min(1,gain)),startupMs);active=next;
            if(prior!=null)cancelLocked(prior);
            writer.execute(()->run(next));
        }
        if(prior!=null){abortSink(prior);emit(prior,"failed",0);}
    }
    void chunk(String id,long cursor,byte[] pcm){
        synchronized(guard){
            State s=current(id);
            if(s==null || cursor<=s.cursor)return; // stale/duplicate events cannot replay audio.
            if(s.ended || pcm==null || pcm.length==0 || pcm.length>MAX_CHUNK || pcm.length%2!=0 || s.total+pcm.length>MAX_BYTES)throw new IllegalArgumentException("Invalid PCM chunk");
            s.cursor=cursor;s.lastInput=System.nanoTime();s.total+=pcm.length;s.queued+=pcm.length;
            s.queue.add(pcm.clone());guard.notifyAll();
        }
    }
    void volume(String id,double gain){if(!Double.isFinite(gain))throw new IllegalArgumentException("Invalid gain");synchronized(guard){State s=current(id);if(s!=null){s.gain=Math.max(0,Math.min(1,gain));if(s.sink!=null)s.sink.gain(s.gain);}}}
    void end(String id,long cursor){
        synchronized(guard){State s=current(id);if(s==null || cursor<=s.cursor)return;s.cursor=cursor;s.ended=true;s.lastInput=System.nanoTime();guard.notifyAll();}
    }
    void abort(String id){
        State s;
        synchronized(guard){s=current(id);if(s==null)return;cancelLocked(s);}
        abortSink(s);emit(s,"failed",0);
    }
    void stop(){State s;synchronized(guard){s=active;if(s!=null)cancelLocked(s);}if(s!=null){abortSink(s);emit(s,"failed",0);}}
    State current(String id){return active!=null && active.id.equals(id) && !active.cancelled && !active.terminal?active:null;}
    void cancelLocked(State s){s.cancelled=true;s.queue.clear();s.queued=0;retire(s.id);guard.notifyAll();}
    void retire(String id){retired.add(id);while(retired.size()>32)retired.remove(retired.iterator().next());}
    void abortSink(State s){Sink sink=s.sink;if(sink!=null)try{sink.abort();}catch(Exception ignored){}}
    void emit(State s,String kind,int underruns){
        synchronized(guard){
            if(kind.equals("started")){if(s.cancelled || s.reportedTerminal)return;}
            else {if(s.reportedTerminal)return;s.reportedTerminal=true;}
        }
        events.accept(kind,s.id,underruns);
    }
    void run(State s){
        Sink sink=null;
        String outcome="failed";
        int underruns=0;
        try{
            synchronized(guard){
                while(!s.cancelled && !s.ended && s.queued<s.prebufferBytes)waitInput(s);
                if(s.cancelled || s.total==0)return;
            }
            sink=factory.create();s.sink=sink;sink.open(s.gain);
            while(true){
                byte[] pcm;
                synchronized(guard){
                    while(!s.cancelled && s.queue.isEmpty() && !s.ended){noteStarted(s,sink);waitInput(s);}
                    if(s.cancelled)return;
                    pcm=s.queue.poll();
                    if(pcm==null)break;
                    s.queued-=pcm.length;
                }
                for(int offset=0;offset<pcm.length;offset+=4800){
                    if(s.cancelled)return;
                    byte[] packet=Arrays.copyOfRange(pcm,offset,Math.min(offset+4800,pcm.length));
                    sink.write(packet);s.written+=packet.length/2;
                    noteStarted(s,sink);
                }
            }
            sink.finishInput();
            long deadline=System.nanoTime()+35_000_000_000L;
            while(!s.cancelled && sink.playedFrames()<s.written && System.nanoTime()<deadline){noteStarted(s,sink);Thread.sleep(10);}
            noteStarted(s,sink);
            if(!s.cancelled && sink.playedFrames()>=s.written){outcome="completed";underruns=sink.underruns();}
        }catch(Exception ignored){
            if(sink!=null)try{sink.abort();}catch(Exception ignoredAgain){}
        }finally{
            if(sink!=null)try{sink.close();}catch(Exception ignored){}
            synchronized(guard){s.terminal=true;retire(s.id);if(active==s)active=null;}
            emit(s,outcome,underruns);
        }
    }
    void noteStarted(State s,Sink sink){
        if(!s.started && !s.cancelled && sink.playedFrames()>0){s.started=true;emit(s,"started",sink.underruns());}
    }
    void waitInput(State s)throws InterruptedException{
        if(System.nanoTime()-s.lastInput>15_000_000_000L)throw new IllegalStateException("Stream stalled");
        guard.wait(100);
    }
    @Override public void close(){synchronized(guard){closed=true;}stop();writer.shutdownNow();}
}
