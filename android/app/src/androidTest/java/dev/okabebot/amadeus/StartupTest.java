package dev.okabebot.amadeus;

import android.widget.*;
import android.view.*;
import androidx.test.rule.ActivityTestRule;
import androidx.test.runner.AndroidJUnit4;
import org.junit.*;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Fresh install is offline and never requests a microphone or contacts the backend. */
@RunWith(AndroidJUnit4.class)
public class StartupTest {
    @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class);
    @Test public void freshInstallHasNoBackendOrMicrophoneBridge() throws Throwable {
        MainActivity app = activity.getActivity();
        activity.runOnUiThread(()->{
            assertEquals(android.content.pm.PackageManager.PERMISSION_GRANTED, app.checkSelfPermission(android.Manifest.permission.MODIFY_AUDIO_SETTINGS));
            assertEquals("",Client.prefs(app).getString("backend",""));
            assertFalse(Client.prefs(app).getBoolean("notifications",false));
            assertNull(app.web);
            assertEquals(4,app.nav.getChildCount());
            assertTrue(app.body.getChildAt(2) instanceof EditText);
            assertTrue(Client.secret(app).matches("[a-f0-9]{64}"));
            assertEquals(Client.secret(app),Client.secret(app));
        });
    }
}
