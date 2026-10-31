package dev.okabebot.amadeus;

import android.Manifest;
import android.app.Activity;
import android.app.PictureInPictureParams;
import android.content.Intent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;
import android.os.PowerManager;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Rational;
import android.view.View;
import android.webkit.*;
import android.widget.*;
import com.google.firebase.messaging.FirebaseMessaging;
import org.json.*;
import java.io.ByteArrayInputStream;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    final ExecutorService io = Executors.newSingleThreadExecutor();
    LinearLayout root, body, nav;
    TextView status;
    WebView web;
    ReplyPlayer replyPlayer;
    StreamReplyPlayer streamPlayer;
    final java.util.concurrent.atomic.AtomicLong nativeAudioGeneration=new java.util.concurrent.atomic.AtomicLong();
    PermissionRequest micRequest;
    String page = "Companion";
    boolean waitingApproval=false, foreground=false;
    final android.os.Handler main = new android.os.Handler(android.os.Looper.getMainLooper());
    volatile String receiverTransition="";
    final java.util.concurrent.ScheduledExecutorService lease = Executors.newSingleThreadScheduledExecutor();
    final BroadcastReceiver screenOff = new BroadcastReceiver(){
        @Override public void onReceive(Context context, Intent intent){releaseScreen();}
    };
    boolean screenAwake(){return ((PowerManager)getSystemService(POWER_SERVICE)).isInteractive();}
    void releaseScreen(){
        nativeAudioGeneration.incrementAndGet();replyPlayer.stop();if(streamPlayer!=null)streamPlayer.stop();
        String transition=receiverTransition;receiverTransition="";
        if(web!=null)web.evaluateJavascript("window.dispatchEvent(new Event('companion-sleep'))",null);
        if(!transition.isEmpty())lease.execute(()->{try{Client.request(this,"/surfaces/closed",new JSONObject().put("transition_id",transition));}catch(Exception ignored){}});
    }
    long lastAudioHeartbeat=0;
    int generation = 0;
    final int ink = Color.rgb(16,30,37), accent = Color.rgb(165,244,206);
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); MessagingService.channel(this);replyPlayer=new ReplyPlayer(this);
        streamPlayer=new StreamReplyPlayer(event->runOnUiThread(()->{if(web!=null)web.evaluateJavascript("window.dispatchEvent(new CustomEvent('companion-stream',{detail:"+event.toString()+"}))",null);}));
        if (getIntent().getBooleanExtra("open_inbox", false) || getIntent().hasExtra("event_id")) page = "Inbox";
        if(Build.VERSION.SDK_INT>=33)registerReceiver(screenOff,new IntentFilter(Intent.ACTION_SCREEN_OFF),Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(screenOff,new IntentFilter(Intent.ACTION_SCREEN_OFF));
        lease.scheduleWithFixedDelay(()->{
            if(receiverTransition.isEmpty() || !screenAwake() || isFinishing())return;
            runOnUiThread(()->{if(web!=null && !isDestroyed() && screenAwake())web.evaluateJavascript("window.dispatchEvent(new Event('companion-audio-poll'))",null);});
            long now=android.os.SystemClock.elapsedRealtime();
            if(now-lastAudioHeartbeat>=4000){lastAudioHeartbeat=now;try{Client.request(this,"/surfaces/heartbeat",new JSONObject());}catch(Exception ignored){}}
        },1,1,java.util.concurrent.TimeUnit.SECONDS);
        render();
    }
    TextView text(String value, int size) {
        TextView t = new TextView(this); t.setText(value); t.setTextColor(accent); t.setTextSize(size);
        t.setTypeface(Typeface.MONOSPACE); t.setPadding(12,12,12,12); return t;
    }
    Button button(String label, Runnable run) {
        Button b = new Button(this); b.setText(label); b.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        b.setTextColor(accent); b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(ink));
        b.setOnClickListener(v -> run.run()); b.setContentDescription(label); return b;
    }
    void destroyWeb() {
        if (web != null) { web.removeJavascriptInterface("AmadeusAndroid"); web.loadUrl("about:blank"); web.destroy(); web=null; }
        if (micRequest != null) { micRequest.deny(); micRequest=null; }
    }
    void render() {
        waitingApproval=false;
        generation++;
        if(web!=null && web.getParent() instanceof android.view.ViewGroup)((android.view.ViewGroup)web.getParent()).removeView(web);
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(ink);
        // Respect system bars rather than putting controls beneath them.
        root.setOnApplyWindowInsetsListener((v,insets) -> { v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom()); return insets; });
        status = text("Amadeus · " + page, 14); root.addView(status);
        body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL); root.addView(body,new LinearLayout.LayoutParams(-1,0,1));
        nav = new LinearLayout(this);
        for (String name : new String[]{"Companion","Chat","Inbox","Setup"}) nav.addView(button(name,()->{page=name;render();}),new LinearLayout.LayoutParams(0,-2,1));
        root.addView(nav); setContentView(root);
        if (Client.prefs(this).getString("backend", "").isEmpty() || page.equals("Setup")) setup();
        else if (page.equals("Companion")) companion();
        else if (page.equals("Chat")) chat();
        else inbox();
        if(!page.equals("Companion") && web!=null){web.setAlpha(0);root.addView(web,0,new LinearLayout.LayoutParams(1,1));}
    }
    void work(Task task, Result result) {work(task,result,null);}
    void work(Task task, Result result, Runnable failed) {
        final int current = generation;
        io.execute(() -> { try { JSONObject value = task.run(); runOnUiThread(()->{if(!isDestroyed() && generation==current)result.done(value);}); }
            catch(Exception e) { runOnUiThread(()->{if(!isDestroyed() && generation==current){status.setText(e.getMessage()==null?"Connection unavailable. Check Tailscale and the Mac.":e.getMessage());if(failed!=null)failed.run();if(waitingApproval)main.postDelayed(this::pollApproval,2000);}}); } });
    }
    interface Task { JSONObject run() throws Exception; } interface Result { void done(JSONObject value); }
    void setup() {
        body.addView(text("Your pocket companion",22));
        body.addView(text("Connect Tailscale on both devices. Enter the Mac’s HTTPS address, then approve this screen in dashboard → Locations. No owner access key is needed.",15));
        EditText url = new EditText(this); url.setSingleLine(true); url.setTextColor(accent); url.setHintTextColor(Color.LTGRAY);
        url.setHint("https://your-mac.your-tailnet.ts.net"); url.setText(Client.prefs(this).getString("backend",""));
        url.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI); body.addView(url);
        Switch notify = new Switch(this); notify.setText("Enable notifications"); notify.setTextColor(accent); notify.setChecked(Client.prefs(this).getBoolean("notifications",false)); body.addView(notify);
        body.addView(text("Show notification alerts without sound. You can change sound in Android notification settings.",14));
        body.addView(button("Save & connect",()->{
            try {
                String base = Endpoint.normalize(url.getText().toString());
                String previous = Client.prefs(this).getString("backend", "");
                if (!previous.isEmpty() && !previous.equals(base)) { status.setText("Changing servers needs a fresh pairing. Clear app storage first to avoid sending an existing device credential to another server."); return; }
                Client.prefs(this).edit().putString("backend",base).putBoolean("notifications",notify.isChecked()).apply();
                if (notify.isChecked()) {
                    if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)
                        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},2);
                    FirebaseMessaging.getInstance().setAutoInitEnabled(true);
                    FirebaseMessaging.getInstance().getToken().addOnSuccessListener(token->{Client.prefs(this).edit().putString("fcm_token",token).apply(); syncPush(true);});
                } else { FirebaseMessaging.getInstance().setAutoInitEnabled(false); syncPush(true); }
                waitingApproval=true; pollApproval();
            } catch(Exception e) {status.setText(e.getMessage());}
        }));
        body.addView(text("Microphone access is requested only when you enable it in Companion. No background recording, location or Bluetooth permissions are used. Chat can read connected context and learn preferences under your private Amadeus consent settings; home controls are unavailable.",14));
    }
    void syncPush() { io.execute(()->{try{Client.syncPush(this);}catch(Exception ignored){}}); }
    void syncPush(boolean explicit) { io.execute(()->{try{Client.syncPush(this,explicit);}catch(Exception ignored){}}); }
    void pollApproval() {
        if(!waitingApproval || isDestroyed())return;
        if(!foreground){main.postDelayed(this::pollApproval,1500);return;}
        work(()->Client.request(this,"/surfaces/register",new JSONObject().put("kind","android").put("name","Android companion")),r->{
            if(!waitingApproval)return;
            if(r.optBoolean("approved")){waitingApproval=false;syncPush();page="Companion";render();}
            else {status.setText("Approve Android companion in dashboard → Locations. This screen will continue automatically.");main.postDelayed(this::pollApproval,1500);}
        });
    }
    void companion() {
        String base = Client.prefs(this).getString("backend", "");
        if(web!=null){web.setAlpha(1);body.addView(web,new LinearLayout.LayoutParams(-1,-1));return;}
        web = new WebView(this); web.setBackgroundColor(ink);
        web.getSettings().setJavaScriptEnabled(true); web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false); web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.getSettings().setMediaPlaybackRequiresUserGesture(true);
        web.addJavascriptInterface(new Object(){
            @JavascriptInterface public boolean supportsAudioStream(){return true;}
            @JavascriptInterface public void streamEvent(String json,double gain){long generation=nativeAudioGeneration.get();runOnUiThread(()->{if(generation==nativeAudioGeneration.get())acceptStreamEvent(json,gain);});}
            @JavascriptInterface public void stopStream(){nativeAudioGeneration.incrementAndGet();runOnUiThread(()->streamPlayer.stop());}
            @JavascriptInterface public void playReply(String encoded, double gain){nativeAudioGeneration.incrementAndGet();runOnUiThread(()->{streamPlayer.stop();replyPlayer.play(encoded,gain,result->{if(web!=null)web.evaluateJavascript("window.dispatchEvent(new CustomEvent('companion-audio',{detail:'"+result+"'}))",null);});});}
            @JavascriptInterface public void receiverLease(String transition){updateReceiverLease(transition);}
            @JavascriptInterface public String deviceToken(){return Client.secret(MainActivity.this);}
            @JavascriptInterface public boolean microphoneGranted(){return checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;}
            @JavascriptInterface public void pictureInPicture(){runOnUiThread(()->enterPictureInPictureMode(new PictureInPictureParams.Builder().setAspectRatio(new Rational(1,1)).build()));}
        },"AmadeusAndroid");
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest r){return !Endpoint.sameOrigin(base,r.getUrl().toString());}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest r){
                if(!Endpoint.sameOrigin(base,r.getUrl().toString())) return new WebResourceResponse("text/plain","UTF-8",403,"Forbidden",java.util.Map.of(),new ByteArrayInputStream(new byte[0]));
                return null;
            }
            @Override public void onPageFinished(WebView view,String url){syncPush();}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())status.setText("Companion disconnected. Check Tailscale and the Mac; retry by reopening this tab.");}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public void onPermissionRequest(PermissionRequest request){runOnUiThread(()->{
                if(!Endpoint.sameOrigin(base,request.getOrigin().toString()) || java.util.Arrays.stream(request.getResources()).anyMatch(r->!r.equals(PermissionRequest.RESOURCE_AUDIO_CAPTURE))){request.deny();return;}
                if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED)request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                else { if(micRequest!=null)micRequest.deny(); micRequest=request;requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},1); }
            });}
            @Override public void onPermissionRequestCanceled(PermissionRequest request){if(micRequest==request)micRequest=null;}
        });
        body.addView(web,new LinearLayout.LayoutParams(-1,-1));
        web.loadUrl(base+"/companion/?android=1");
    }
    void updateReceiverLease(String transition){
        String previous=receiverTransition;
        receiverTransition=screenAwake() && transition!=null && transition.matches("[A-Za-z0-9_-]{1,128}")?transition:"";
        if(!previous.isEmpty() && receiverTransition.isEmpty()){
            nativeAudioGeneration.incrementAndGet();
            runOnUiThread(()->{if(receiverTransition.isEmpty()){streamPlayer.stop();replyPlayer.stop();}});
        }
    }
    void acceptStreamEvent(String json,double gain){
        // Stream start/stop and screen release share the UI queue; late queued starts cannot resurrect audio.
        if(isDestroyed() || isFinishing() || !screenAwake() || receiverTransition.isEmpty()){
            streamPlayer.stop();return;
        }
        try{if(new JSONObject(json).optString("kind").equals("start"))replyPlayer.stop();}catch(Exception ignored){}
        streamPlayer.event(json,gain);
    }
    void suggestionCard(){
        final SuggestionCard[] card={null};
        card[0]=new SuggestionCard(this,(id,outcome)->work(
            ()->Client.request(this,"/mobile/feedback",new JSONObject().put("suggestion_id",id).put("outcome",outcome)),
            r->{if(r.optBoolean("saved"))card[0].saved(r.optString("outcome",outcome));else card[0].uncertain();},
            ()->card[0].uncertain()));
        body.addView(card[0]);
        work(()->Client.request(this,"/mobile/suggestion",null),r->card[0].show(r),()->card[0].unavailable());
    }
    void chat() {
        suggestionCard();
        TextView transcript=text("Ask about connected home context, your watchlist, or share a preference. Home controls are unavailable here.",16);
        ScrollView scroll=new ScrollView(this);scroll.addView(transcript);body.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        EditText message=new EditText(this);message.setTextColor(accent);message.setHintTextColor(Color.LTGRAY);message.setHint("Message Amadeus");message.setMaxLines(4);body.addView(message);
        Button send=button("Send",()->{});body.addView(send);
        send.setOnClickListener(v->{String value=message.getText().toString().trim();if(value.isEmpty()||value.length()>1000)return;
            send.setEnabled(false);message.setText("");transcript.append("\n\nYou: "+value);status.setText("Thinking…");
            work(()->Client.request(this,"/mobile/chat",new JSONObject().put("text",value).put("request_id",UUID.randomUUID().toString())),r->{transcript.append("\n\nAmadeus: "+r.optString("reply"));send.setEnabled(true);status.setText("Amadeus · Chat");scroll.post(()->scroll.fullScroll(View.FOCUS_DOWN));});
            // Errors leave the uncertain request disabled; switching tabs starts a fresh turn, never a replay.
        });
    }
    void inbox() {
        suggestionCard();
        TextView content=text("Connecting privately…",16);ScrollView scroll=new ScrollView(this);scroll.addView(content);body.addView(scroll);
        work(()->Client.request(this,"/mobile/inbox",null),r->{JSONArray items=r.optJSONArray("items");content.setText("");
            if(items==null||items.length()==0)content.setText("No recent notes. Notifications appear here after this phone is approved and notifications are enabled.");
            else for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item!=null)content.append(item.optString("title")+"\n"+item.optString("body")+"\n\n────────────────\n\n");}
        });
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){
        super.onRequestPermissionsResult(request,permissions,grants);
        if(request==1 && micRequest!=null){if(grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED)micRequest.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});else micRequest.deny();micRequest=null;}
        if(request==2 && (grants.length==0||grants[0]!=PackageManager.PERMISSION_GRANTED)){Client.prefs(this).edit().putBoolean("notifications",false).apply();syncPush(true);}
    }
    @Override public void onPictureInPictureModeChanged(boolean pip,android.content.res.Configuration config){super.onPictureInPictureModeChanged(pip,config);nav.setVisibility(pip?View.GONE:View.VISIBLE);status.setVisibility(pip?View.GONE:View.VISIBLE);}
    @Override protected void onResume(){super.onResume();foreground=true;}
    @Override protected void onPause(){super.onPause();foreground=false;if(web!=null)web.evaluateJavascript("window.dispatchEvent(new Event('blur'))",null);}
    @Override protected void onStop(){super.onStop();if(isFinishing() || !screenAwake())releaseScreen();}
    @Override protected void onRestart(){super.onRestart();}
    @Override protected void onDestroy(){releaseScreen();streamPlayer.close();unregisterReceiver(screenOff);lease.shutdown();waitingApproval=false;main.removeCallbacksAndMessages(null);destroyWeb();io.shutdownNow();super.onDestroy();}
}
