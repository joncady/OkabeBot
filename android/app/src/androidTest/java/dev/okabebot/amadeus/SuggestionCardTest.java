package dev.okabebot.amadeus;

import androidx.test.rule.ActivityTestRule;
import androidx.test.runner.AndroidJUnit4;
import org.junit.*;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Invented receipt only; no account, model, audio or backend connection. */
@RunWith(AndroidJUnit4.class)
public class SuggestionCardTest {
    @Rule public ActivityTestRule<MainActivity> activity=new ActivityTestRule<>(MainActivity.class);
    @Test public void feedbackBindsTheVisibleReceiptAndPreventsDoubleSubmit() throws Throwable {
        AtomicInteger count=new AtomicInteger();AtomicReference<String> submitted=new AtomicReference<>();
        activity.runOnUiThread(()->{
            SuggestionCard card=new SuggestionCard(activity.getActivity(),(id,outcome)->{count.incrementAndGet();submitted.set(id+":"+outcome);});
            String id="abcdef0123456789abcdef0123456789";
            try{card.show(new JSONObject().put("available",true).put("suggestion",new JSONObject().put("id",id).put("topic","interests").put("reason","An older interest, outside protected time.")));}catch(Exception e){throw new AssertionError(e);}
            assertEquals(android.view.View.GONE,card.reason.getVisibility());card.why.performClick();assertEquals(android.view.View.VISIBLE,card.reason.getVisibility());
            card.choices.getChildAt(1).performClick();card.choices.getChildAt(1).performClick();
            assertEquals(1,count.get());assertEquals(id+":too_soon",submitted.get());
            card.uncertain();assertFalse(card.choices.getChildAt(0).isEnabled());assertTrue(card.message.getText().toString().contains("not confirmed"));
        });
    }
    @Test public void absentOrMalformedReceiptCannotSendFeedback() throws Throwable {
        AtomicInteger count=new AtomicInteger();
        activity.runOnUiThread(()->{
            SuggestionCard card=new SuggestionCard(activity.getActivity(),(id,outcome)->count.incrementAndGet());
            try{card.show(new JSONObject().put("available",false));}catch(Exception e){throw new AssertionError(e);}
            card.choices.getChildAt(0).performClick();assertEquals(0,count.get());
            try{card.show(new JSONObject().put("available",true).put("suggestion",new JSONObject().put("id","bad")));}catch(Exception e){throw new AssertionError(e);}
            assertEquals("",card.suggestionId);assertEquals(android.view.View.GONE,card.choices.getVisibility());
        });
    }
}
