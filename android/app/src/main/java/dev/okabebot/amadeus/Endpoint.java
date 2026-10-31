package dev.okabebot.amadeus;

import java.net.URI;
import java.util.Locale;

/** Only the private, certificate-validated Tailscale HTTPS origin is accepted. */
public final class Endpoint {
    public static String normalize(String value) {
        try {
            URI u = new URI(value.trim());
            String host = u.getHost();
            if (!"https".equalsIgnoreCase(u.getScheme()) || host == null
                    || !host.toLowerCase(Locale.ROOT).endsWith(".ts.net") || u.getRawUserInfo() != null
                    || (u.getPort() != -1 && u.getPort() != 443)
                    || u.getRawQuery() != null || u.getRawFragment() != null
                    || !(u.getPath().isEmpty() || u.getPath().equals("/"))) {
                throw new IllegalArgumentException();
            }
            return "https://" + host.toLowerCase(Locale.ROOT);
        } catch (Exception e) {
            throw new IllegalArgumentException("Use the Mac’s https://…ts.net address, without a path or access key.");
        }
    }
    public static boolean sameOrigin(String base, String value) {
        try {
            URI u = new URI(value);
            return normalize(base).equals(normalize("https://" + u.getRawAuthority()))
                    && "https".equalsIgnoreCase(u.getScheme());
        } catch (Exception e) { return false; }
    }
}
