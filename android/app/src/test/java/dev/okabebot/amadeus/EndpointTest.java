package dev.okabebot.amadeus;
import org.junit.Test;
import static org.junit.Assert.*;
public class EndpointTest {
    @Test public void acceptsOnlyPrivateHttpsOrigin() {
        assertEquals("https://lab.example.ts.net",Endpoint.normalize("https://lab.example.ts.net/"));
        for (String bad : new String[]{"http://lab.example.ts.net","https://evil.example","https://lab.example.ts.net.evil.test","https://user:pass@lab.example.ts.net","https://lab.example.ts.net/#key","https://lab.example.ts.net/?token=abc","https://lab.example.ts.net/path","https://lab.example.ts.net:8768"}) {
            try { Endpoint.normalize(bad); fail(bad); } catch (IllegalArgumentException expected) {}
        }
        assertTrue(Endpoint.sameOrigin("https://lab.example.ts.net","https://lab.example.ts.net/companion/?android=1"));
        assertFalse(Endpoint.sameOrigin("https://lab.example.ts.net","http://lab.example.ts.net/companion/"));
        assertFalse(Endpoint.sameOrigin("https://lab.example.ts.net","https://other.example.ts.net/"));
    }
}
