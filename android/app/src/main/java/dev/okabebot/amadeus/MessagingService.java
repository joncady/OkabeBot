package dev.okabebot.amadeus;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public final class MessagingService extends FirebaseMessagingService {
    static void channel(android.content.Context c) {
        NotificationChannel ch = new NotificationChannel("amadeus_notes", "Amadeus notes", NotificationManager.IMPORTANCE_LOW);
        ch.setDescription("Quiet notes from your companion; personal content is fetched privately when opened.");
        c.getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }
    @Override public void onNewToken(String token) {
        Client.prefs(this).edit().putString("fcm_token", token).apply();
        try { Client.syncPush(this); } catch (Exception ignored) { /* Latest token syncs on next foreground connection. */ }
    }
    @Override public void onMessageReceived(RemoteMessage message) {
        if (!Client.prefs(this).getBoolean("notifications", false)) return;
        String id = message.getData().get("event_id");
        if (id == null || !id.matches("[a-f0-9]{32}")) return;
        channel(this);
        Intent intent = new Intent(this, MainActivity.class).putExtra("open_inbox", true);
        PendingIntent tap = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, "amadeus_notes").setSmallIcon(R.drawable.ic_note)
                .setContentTitle("Amadeus").setContentText("A new note is waiting.")
                .setVisibility(Notification.VISIBILITY_PRIVATE).setContentIntent(tap).setAutoCancel(true).build();
        getSystemService(NotificationManager.class).notify(id, 0, n);
    }
}
