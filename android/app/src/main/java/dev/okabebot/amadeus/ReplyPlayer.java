package dev.okabebot.amadeus;

import android.content.Context;
import android.media.*;
import android.util.Base64;
import java.io.File;
import java.nio.file.Files;
import java.util.function.Consumer;

/** Private reply playback independent of WebView autoplay and AudioContext lifecycle. */
final class ReplyPlayer {
    final Context context;
    MediaPlayer player;
    File clip;
    Consumer<String> callback;
    ReplyPlayer(Context context){this.context=context;}
    void play(String encoded, double gain, Consumer<String> result){
        stop();callback=result;
        try{
            if(encoded.length()>2000000 || !Double.isFinite(gain))throw new IllegalArgumentException();
            byte[] wav=Base64.decode(encoded,Base64.DEFAULT);
            if(wav.length<44 || wav[0]!='R' || wav[1]!='I' || wav[2]!='F' || wav[3]!='F')throw new IllegalArgumentException();
            clip=File.createTempFile("reply-",".wav",context.getCacheDir());
            Files.write(clip.toPath(),wav);
            player=new MediaPlayer();
            player.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
            player.setVolume((float)Math.max(0,Math.min(1,gain)),(float)Math.max(0,Math.min(1,gain)));
            player.setOnPreparedListener(p->{p.start();result.accept("started");});
            player.setOnCompletionListener(p->{callback=null;stop();result.accept("completed");});
            player.setOnErrorListener((p,what,extra)->{callback=null;stop();result.accept("failed");return true;});
            player.setDataSource(clip.getAbsolutePath());player.prepareAsync();
        }catch(Exception e){callback=null;stop();result.accept("failed");}
    }
    void stop(){
        Consumer<String> old=callback;callback=null;
        if(player!=null){player.release();player=null;}
        if(clip!=null){clip.delete();clip=null;}
        if(old!=null)old.accept("failed");
    }
}
