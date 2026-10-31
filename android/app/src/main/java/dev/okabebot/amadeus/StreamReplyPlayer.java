package dev.okabebot.amadeus;

import android.media.*;
import org.json.JSONObject;
import java.util.function.Consumer;

/** AudioHub PCM events to a continuous native Android output, never files or networking. */
final class StreamReplyPlayer implements AutoCloseable {
    final PcmStreamEngine engine;
    final Consumer<JSONObject> events;
    StreamReplyPlayer(Consumer<JSONObject> events){
        this.events=events;
        engine=new PcmStreamEngine(Track::new,(kind,id,underruns)->{
            try{events.accept(new JSONObject().put("kind",kind).put("stream_id",id).put("underruns",underruns));}catch(Exception ignored){}
        });
    }
    void event(String json,double gain){
        String id="";
        try{
            if(json==null || json.length()>330000)throw new IllegalArgumentException();
            JSONObject data=new JSONObject(json);
            id=data.getString("stream_id");
            String kind=data.getString("kind");
            if(kind.equals("volume")){engine.volume(id,gain);return;}
            long cursor=data.getLong("cursor");
            if(cursor<0)throw new IllegalArgumentException();
            switch(kind){
                case "start":
                    if(data.optInt("sample_rate",24000)!=24000 || data.optInt("channels",1)!=1 || !data.optString("encoding","pcm_s16le").equals("pcm_s16le"))throw new IllegalArgumentException();
                    engine.start(id,cursor,gain,data.optInt("startup_buffer_ms",240));break;
                case "chunk":
                    String encoded=data.getString("pcm_base64");
                    if(encoded.length()>320000)throw new IllegalArgumentException();
                    byte[] pcm=java.util.Base64.getDecoder().decode(encoded);
                    if(pcm.length==0 || pcm.length%2!=0 || pcm.length>PcmStreamEngine.MAX_CHUNK)throw new IllegalArgumentException();
                    engine.chunk(id,cursor,pcm);break;
                case "end":engine.end(id,cursor);break;
                case "abort":engine.abort(id);break;
                default:throw new IllegalArgumentException();
            }
        }catch(Exception e){
            engine.abort(id);
            try{events.accept(new JSONObject().put("kind","failed").put("stream_id",id));}catch(Exception ignored){}
        }
    }
    void stop(){engine.stop();}
    @Override public void close(){engine.close();}
    static final class Track implements PcmStreamEngine.Sink {
        volatile AudioTrack track;
        volatile boolean aborted;
        long writtenBytes;
        @Override public void open(double gain){
            int minimum=AudioTrack.getMinBufferSize(PcmStreamEngine.SAMPLE_RATE,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT);
            if(minimum<=0)throw new IllegalStateException("Audio unavailable");
            AudioTrack value=new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(PcmStreamEngine.SAMPLE_RATE).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(Math.max(minimum,1920)).build();
            if(value.getState()!=AudioTrack.STATE_INITIALIZED){value.release();throw new IllegalStateException("Audio unavailable");}
            if(android.os.Build.VERSION.SDK_INT>=31)value.setStartThresholdInFrames(Math.min(480,value.getBufferCapacityInFrames()));
            track=value;value.setVolume((float)gain);value.play();
        }
        @Override public void write(byte[] pcm){
            AudioTrack value=track;if(value==null)throw new IllegalStateException("Audio cancelled");
            int offset=0;
            while(offset<pcm.length){if(aborted)throw new IllegalStateException("Audio cancelled");int wrote=value.write(pcm,offset,pcm.length-offset,AudioTrack.WRITE_BLOCKING);if(wrote<=0)throw new IllegalStateException("Audio write failed");offset+=wrote;writtenBytes+=wrote;}
        }
        @Override public void finishInput(){
            AudioTrack value=track;
            if(value!=null && value.getPlaybackHeadPosition()==0){
                long missing=value.getBufferCapacityInFrames()*2L-writtenBytes;
                if(missing>0)write(new byte[(int)missing]); // Prime short final clips on pre-31 default thresholds.
            }
        }
        @Override public long playedFrames(){AudioTrack value=track;return value==null?0:Integer.toUnsignedLong(value.getPlaybackHeadPosition());}
        @Override public int underruns(){AudioTrack value=track;return value==null?0:value.getUnderrunCount();}
        @Override public void gain(double gain){AudioTrack value=track;if(value!=null)value.setVolume((float)gain);}
        @Override public void abort(){aborted=true;AudioTrack value=track;if(value!=null){value.pause();value.flush();}}
        @Override public void close(){AudioTrack value=track;track=null;if(value!=null)value.release();}
    }
}
