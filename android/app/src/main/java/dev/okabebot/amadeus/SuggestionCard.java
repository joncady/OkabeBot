package dev.okabebot.amadeus;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.widget.*;
import org.json.JSONObject;

/** Latest delivered check-in only. Feedback is bound to its immutable receipt ID. */
final class SuggestionCard extends LinearLayout {
    interface Submit { void send(String id,String outcome); }
    final TextView heading, message, reason;
    final Button why;
    final LinearLayout choices;
    String suggestionId="";
    boolean submitting;
    final int accent=Color.rgb(165,244,206),ink=Color.rgb(16,30,37);
    SuggestionCard(Context context, Submit submit){
        super(context);setOrientation(VERTICAL);setPadding(10,6,10,6);
        setBackgroundColor(Color.rgb(23,43,51));
        heading=label("Latest check-in",13);addView(heading);
        message=label("Checking for a recent invitation…",12);addView(message);
        why=new Button(context);why.setText("Why this check-in?");style(why);why.setVisibility(GONE);addView(why);
        reason=label("",13);reason.setVisibility(GONE);addView(reason);
        why.setOnClickListener(v->{boolean open=reason.getVisibility()!=VISIBLE;reason.setVisibility(open?VISIBLE:GONE);why.setText(open?"Hide explanation":"Why this check-in?");});
        choices=new LinearLayout(context);choices.setVisibility(GONE);addView(choices);
        String[][] items={{"Good timing","good_timing"},{"Too soon","too_soon"},{"Not interested","not_interested"}};
        for(String[] item:items){Button b=new Button(context);b.setText(item[0]);style(b);choices.addView(b,new LinearLayout.LayoutParams(0,-2,1));
            b.setOnClickListener(v->{if(submitting||suggestionId.isEmpty())return;submitting=true;enabled(false);message.setText("Saving feedback…");submit.send(suggestionId,item[1]);});}
    }
    TextView label(String value,int size){TextView v=new TextView(getContext());v.setText(value);v.setTextColor(accent);v.setTextSize(size);v.setTypeface(Typeface.MONOSPACE);v.setPadding(2,3,2,3);return v;}
    void style(Button b){b.setTextSize(11);b.setTextColor(accent);b.setTypeface(Typeface.MONOSPACE,Typeface.BOLD);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(ink));b.setMinHeight(48);b.setAllCaps(false);}
    void enabled(boolean enabled){for(int i=0;i<choices.getChildCount();i++)choices.getChildAt(i).setEnabled(enabled);}
    void show(JSONObject envelope){
        JSONObject s=envelope.optJSONObject("suggestion");
        suggestionId="";submitting=false;
        if(!envelope.optBoolean("available")||s==null){message.setText("No recent delivered check-in.");why.setVisibility(GONE);reason.setVisibility(GONE);choices.setVisibility(GONE);return;}
        String id=s.optString("id");
        if(!id.matches("[a-f0-9]{32}")){unavailable();return;}
        suggestionId=id;
        double at=s.optDouble("at",Double.NaN);
        heading.setText(Double.isFinite(at)&&at>0?"Latest check-in · "+android.text.format.DateUtils.getRelativeTimeSpanString((long)(at*1000),System.currentTimeMillis(),android.text.format.DateUtils.MINUTE_IN_MILLIS):"Latest check-in");
        String topic=s.isNull("topic")?"":s.optString("topic","");
        message.setText(topic.isEmpty()?"A recent invitation is ready for feedback.":"Topic: "+topic.replace('_',' '));
        String explanation=s.isNull("reason")?"":s.optString("reason","");
        reason.setText(explanation.isEmpty()?"No explanation was recorded for this check-in.":explanation.substring(0,Math.min(explanation.length(),600)));
        reason.setVisibility(GONE);why.setText("Why this check-in?");why.setVisibility(VISIBLE);choices.setVisibility(VISIBLE);enabled(true);
        String feedback=s.optString("feedback","");if(!feedback.isEmpty()&&!feedback.equals("null")){message.setText("Feedback saved: "+feedback.replace('_',' '));enabled(false);}
    }
    void saved(String outcome){submitting=false;message.setText("Feedback saved: "+outcome.replace('_',' '));enabled(false);}
    void uncertain(){submitting=false;message.setText("Feedback not confirmed. Reopen this tab to check before sending again.");enabled(false);}
    void unavailable(){suggestionId="";message.setText("Check-in details unavailable. Reopen this tab to refresh.");why.setVisibility(GONE);reason.setVisibility(GONE);choices.setVisibility(GONE);}
}
