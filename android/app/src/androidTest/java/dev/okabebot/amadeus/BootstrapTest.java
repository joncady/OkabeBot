package dev.okabebot.amadeus;

import android.webkit.*;
import androidx.test.rule.ActivityTestRule;
import androidx.test.runner.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.*;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Real Android WebView bootstrap with invented intercepted responses, no network or microphone. */
@RunWith(AndroidJUnit4.class)
public class BootstrapTest {
    @Rule public ActivityTestRule<MainActivity> activity=new ActivityTestRule<>(MainActivity.class);
    @After public void clear() throws Throwable {
        activity.runOnUiThread(()->Client.prefs(activity.getActivity()).edit().clear().commit());
    }
    @Test public void nativePcmStreamDrainsAndRejectsMalformedAudio() throws Throwable {
        CountDownLatch ended=new CountDownLatch(1);
        AtomicReference<String> result=new AtomicReference<>();
        java.util.List<String> events=new java.util.concurrent.CopyOnWriteArrayList<>();
        StreamReplyPlayer player=new StreamReplyPlayer(event->{String kind=event.optString("kind");events.add(kind);if(kind.equals("completed") || kind.equals("failed")){result.set(kind);ended.countDown();}});
        try{
            player.event("{\"kind\":\"start\",\"stream_id\":\"invented-pcm\",\"cursor\":1}",0);
            String pcm=android.util.Base64.encodeToString(new byte[4800],android.util.Base64.NO_WRAP);
            player.event("{\"kind\":\"chunk\",\"stream_id\":\"invented-pcm\",\"cursor\":2,\"pcm_base64\":\""+pcm+"\"}",0);
            player.event("{\"kind\":\"end\",\"stream_id\":\"invented-pcm\",\"cursor\":3}",0);
            assertTrue(ended.await(10,TimeUnit.SECONDS));assertEquals("completed",result.get());assertTrue(events.contains("started"));
            int count=events.size();player.event("{\"kind\":\"start\",\"stream_id\":\"invented-pcm\",\"cursor\":1}",0);Thread.sleep(50);assertEquals(count,events.size());
            player.event("{\"kind\":\"chunk\",\"stream_id\":\"bad-pcm\",\"cursor\":4,\"pcm_base64\":\"!\"}",0);assertEquals("failed",result.get());
        }finally{player.close();}
    }
    @Test public void lateStartAfterScreenReleaseCannotResurrectNativeAudio() throws Throwable {
        MainActivity app=activity.getActivity();
        activity.runOnUiThread(()->{
            app.receiverTransition="invented-arrival";
            app.acceptStreamEvent("{\"kind\":\"start\",\"stream_id\":\"before-release\",\"cursor\":1}",0);
            app.updateReceiverLease("");
            app.acceptStreamEvent("{\"kind\":\"start\",\"stream_id\":\"after-release\",\"cursor\":2}",0);
            synchronized(app.streamPlayer.engine.guard){
                PcmStreamEngine.State current=app.streamPlayer.engine.active;
                assertTrue(current==null || current.cancelled);
                if(current!=null)assertNotEquals("after-release",current.id);
            }
        });
    }
    @Test public void privateNativeWavReportsCompletionAndDeletesClip() throws Throwable {
        MainActivity app=activity.getActivity();
        java.nio.ByteBuffer wav=java.nio.ByteBuffer.allocate(3244).order(java.nio.ByteOrder.LITTLE_ENDIAN);
        wav.put("RIFF".getBytes()).putInt(3236).put("WAVEfmt ".getBytes()).putInt(16).putShort((short)1).putShort((short)1).putInt(16000).putInt(32000).putShort((short)2).putShort((short)16).put("data".getBytes()).putInt(3200);
        String encoded=android.util.Base64.encodeToString(wav.array(),android.util.Base64.NO_WRAP);
        CountDownLatch ended=new CountDownLatch(1);
        AtomicReference<String> result=new AtomicReference<>();
        activity.runOnUiThread(()->app.replyPlayer.play(encoded,0,state->{if(!state.equals("started")){result.set(state);ended.countDown();}}));
        assertTrue(ended.await(10,TimeUnit.SECONDS));assertEquals("completed",result.get());
        activity.runOnUiThread(()->{assertNull(app.replyPlayer.player);assertNull(app.replyPlayer.clip);});
    }
    @Test public void tabAndAppSwitchKeepTheSameWebView() throws Throwable {
        MainActivity app=activity.getActivity();
        activity.runOnUiThread(()->{
            Client.prefs(app).edit().putString("backend","https://fiction.example.ts.net").commit();
            app.web=new WebView(app); // No URL loaded; no network or microphone.
            WebView original=app.web;
            app.page="Setup";app.render();
            assertSame(original,app.web);
            app.onPause();app.onStop();app.onRestart();app.onResume();
            assertSame(original,app.web);
            app.page="Companion";app.render();
            assertSame(original,app.web);
            app.releaseScreen();
            assertEquals("",app.receiverTransition);
        });
    }
    @Test public void nativeBridgeBootsAndPollsApproval() throws Throwable {
        MainActivity app=activity.getActivity();
        CountDownLatch loaded=new CountDownLatch(1);
        AtomicReference<String> result=new AtomicReference<>();
        activity.runOnUiThread(()->{
            Client.prefs(app).edit().putString("backend","https://fiction.example.ts.net").commit();
            app.page="Companion";app.render();
            app.web.stopLoading();
            app.web.setWebViewClient(new WebViewClient(){
                @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                    String path=request.getUrl().getPath();
                    try {
                        if(path.equals("/surfaces/register"))return new WebResourceResponse("application/json","UTF-8",new ByteArrayInputStream("{\"id\":\"invented\",\"approved\":false,\"name\":\"Invented phone\"}".getBytes()));
                        String file=path.equals("/companion/")?"companion.html":path.substring(1);
                        String mime=file.endsWith(".html")?"text/html":file.endsWith(".css")?"text/css":"application/javascript";
                        return new WebResourceResponse(mime,"UTF-8",InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(file));
                    } catch(Exception e){return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));}
                }
                @Override public void onPageFinished(WebView view,String url){loaded.countDown();}
            });
            app.web.loadUrl("https://fiction.example.ts.net/companion/?android=1");
        });
        assertTrue("Fixture page loaded",loaded.await(10,TimeUnit.SECONDS));
        long end=System.currentTimeMillis()+10000;
        do {
            CountDownLatch read=new CountDownLatch(1);
            activity.runOnUiThread(()->app.web.evaluateJavascript("JSON.stringify({error:document.getElementById('setup-error').textContent,pair:document.getElementById('pair-step').textContent})",value->{result.set(value);read.countDown();}));
            assertTrue(read.await(2,TimeUnit.SECONDS));
            if(result.get()!=null&&result.get().contains("Approve this screen"))return;
            Thread.sleep(100);
        } while(System.currentTimeMillis()<end);
        fail("Screen bootstrap: "+result.get());
    }
}
