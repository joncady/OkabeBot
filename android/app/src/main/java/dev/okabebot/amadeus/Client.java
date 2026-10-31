package dev.okabebot.amadeus;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.SecureRandom;

final class Client {
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("amadeus", Context.MODE_PRIVATE); }
    static String secret(Context c) {
        synchronized (Client.class) {
            String current = prefs(c).getString("device_secret", "");
            if (current.isEmpty()) {
                byte[] raw = new byte[32]; new SecureRandom().nextBytes(raw);
                StringBuilder b = new StringBuilder(); for (byte v : raw) b.append(String.format("%02x", v));
                current = b.toString(); prefs(c).edit().putString("device_secret", current).commit();
            }
            return current;
        }
    }
    static JSONObject request(Context c, String path, JSONObject data) throws Exception {
        String base = Endpoint.normalize(prefs(c).getString("backend", ""));
        HttpURLConnection conn = (HttpURLConnection) new URL(base + path).openConnection();
        conn.setInstanceFollowRedirects(false); conn.setConnectTimeout(10000); conn.setReadTimeout(120000);
        conn.setRequestProperty("X-Surface-Token", secret(c));
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Cache-Control", "no-store");
        try {
            if (data != null) { conn.setRequestMethod("POST"); conn.setDoOutput(true);
                try (var out = conn.getOutputStream()) { out.write(data.toString().getBytes(StandardCharsets.UTF_8)); } }
            int status = conn.getResponseCode();
            if (status < 200 || status >= 300) throw new Exception(status == 403
                    ? "Approve this Android screen in dashboard → Locations first."
                    : "Request could not finish. Check Amadeus consent and backend status; it will not retry automatically.");
            try (InputStream in = conn.getInputStream(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] chunk = new byte[8192]; int n;
                while ((n = in.read(chunk)) != -1) {
                    if (bytes.size() + n > 2_000_000) throw new Exception("Response too large"); bytes.write(chunk, 0, n);
                }
                return new JSONObject(bytes.toString(StandardCharsets.UTF_8.name()));
            }
        } finally { conn.disconnect(); }
    }
    static void syncPush(Context c) throws Exception {
        syncPush(c, false);
    }
    static void syncPush(Context c, boolean explicit) throws Exception {
        String token = prefs(c).getString("fcm_token", "");
        if (!token.isEmpty()) request(c, "/mobile/push", new JSONObject()
                .put("token", token).put("enabled", prefs(c).getBoolean("notifications", false)).put("set_enabled",explicit));
    }
}
