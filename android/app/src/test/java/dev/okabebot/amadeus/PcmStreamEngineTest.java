package dev.okabebot.amadeus;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class PcmStreamEngineTest {
    static class FakeSink implements PcmStreamEngine.Sink {
        volatile long written,played;
        volatile boolean aborted,closed;
        volatile double gain;
        final boolean automatic;
        FakeSink(boolean automatic){this.automatic=automatic;}
        public void open(double value){gain=value;}
        public void write(byte[] pcm){written+=pcm.length/2;if(automatic)played=written;else if(played==0)played=1;}
        public long playedFrames(){return played;}
        public int underruns(){return 0;}
        public void gain(double value){gain=value;}
        public void abort(){aborted=true;}
        public void close(){closed=true;}
    }
    static void waitUntil(java.util.function.BooleanSupplier condition)throws Exception {
        long deadline=System.nanoTime()+2_000_000_000L;
        while(!condition.getAsBoolean() && System.nanoTime()<deadline)Thread.sleep(5);
        assertTrue(condition.getAsBoolean());
    }
    @Test public void prebufferAndEndDrainAreSeparateFromQueueCompletion()throws Exception {
        FakeSink sink=new FakeSink(false);AtomicInteger opened=new AtomicInteger();
        List<String> events=new CopyOnWriteArrayList<>();
        try(PcmStreamEngine engine=new PcmStreamEngine(()->{opened.incrementAndGet();return sink;},(kind,id,u)->events.add(kind))){
            engine.start("fiction",1,.35);engine.chunk("fiction",2,new byte[4800]);
            Thread.sleep(40);assertEquals(0,opened.get());
            engine.end("fiction",3);waitUntil(()->events.contains("started"));
            assertEquals(2400,sink.written);assertFalse(events.contains("completed"));assertEquals(.35,sink.gain,0);
            sink.played=2400;waitUntil(()->events.contains("completed"));assertTrue(sink.closed);
        }
    }
    @Test public void serverStartupOverrideIsHonoredAndShortEndStillPlays()throws Exception {
        FakeSink sink=new FakeSink(true);AtomicInteger opened=new AtomicInteger();List<String> events=new CopyOnWriteArrayList<>();
        try(PcmStreamEngine engine=new PcmStreamEngine(()->{opened.incrementAndGet();return sink;},(kind,id,u)->events.add(kind))){
            engine.start("fiction",1,.4,800);engine.chunk("fiction",2,new byte[24000]);
            Thread.sleep(40);assertEquals(0,opened.get());
            engine.end("fiction",3);waitUntil(()->events.contains("completed"));assertEquals(1,opened.get());
            try{engine.start("other",4,.2,2001);fail();}catch(IllegalArgumentException expected){}
        }
    }
    @Test public void olderSinkCanRequireMoreThanOnePacketBeforePlaybackAdvances()throws Exception {
        FakeSink sink=new FakeSink(false){
            @Override public void write(byte[] pcm){written+=pcm.length/2;if(written>=4800)played=written;}
        };
        List<String> events=new CopyOnWriteArrayList<>();
        try(PcmStreamEngine engine=new PcmStreamEngine(()->sink,(kind,id,u)->events.add(kind))){
            engine.start("fiction",1,.2);engine.chunk("fiction",2,new byte[12000]);engine.end("fiction",3);
            waitUntil(()->events.contains("completed"));
            assertTrue(events.contains("started"));assertEquals(6000,sink.written);assertFalse(events.contains("failed"));
        }
    }
    @Test public void duplicateAndRetiredStreamsCannotReplayAndBadPcmIsRejected()throws Exception {
        List<String> events=new CopyOnWriteArrayList<>();FakeSink sink=new FakeSink(true);AtomicInteger opened=new AtomicInteger();
        try(PcmStreamEngine engine=new PcmStreamEngine(()->{opened.incrementAndGet();return sink;},(kind,id,u)->events.add(kind))){
            engine.start("fiction",1,2);engine.chunk("fiction",2,new byte[12000]);engine.chunk("fiction",2,new byte[12000]);
            engine.chunk("not-current",20,new byte[12000]);
            try{engine.chunk("fiction",3,new byte[3]);fail();}catch(IllegalArgumentException expected){}
            engine.end("fiction",3);waitUntil(()->events.contains("completed"));
            assertEquals(6000,sink.written);assertEquals(1,sink.gain,0);
            engine.start("fiction",1,.2);Thread.sleep(20);assertEquals(1,opened.get());
        }
    }
    @Test public void cancellationFlushesPendingAudioAndNeverCompletes()throws Exception {
        List<String> events=new CopyOnWriteArrayList<>();FakeSink sink=new FakeSink(false);
        try(PcmStreamEngine engine=new PcmStreamEngine(()->sink,(kind,id,u)->events.add(kind))){
            engine.start("fiction",1,.3);engine.chunk("fiction",2,new byte[12000]);engine.end("fiction",3);
            waitUntil(()->events.contains("started"));engine.stop();waitUntil(()->events.contains("failed") && sink.closed);
            assertTrue(sink.aborted);assertTrue(sink.closed);assertFalse(events.contains("completed"));
        }
    }
    @Test public void totalPcmIsBoundedAndVolumeCanChangeWithoutRestart()throws Exception {
        FakeSink sink=new FakeSink(true);
        try(PcmStreamEngine engine=new PcmStreamEngine(()->sink,(kind,id,u)->{})){
            engine.start("fiction",1,.3);engine.chunk("fiction",2,new byte[12000]);waitUntil(()->sink.written>0);
            engine.volume("fiction",.7);assertEquals(.7,sink.gain,0);
            long cursor=3;for(int i=0;i<5;i++)engine.chunk("fiction",cursor++,new byte[240000]);
            try{engine.chunk("fiction",cursor,new byte[240000]);fail();}catch(IllegalArgumentException expected){}
            assertTrue(engine.active.queued<=PcmStreamEngine.MAX_BYTES);
        }
    }
}
