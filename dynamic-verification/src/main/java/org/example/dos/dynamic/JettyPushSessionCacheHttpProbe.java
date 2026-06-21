package org.example.dos.dynamic;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlets.PushSessionCacheFilter;

public final class JettyPushSessionCacheHttpProbe {
    private static String pathToken(int index, int payloadBytes) {
        int retainedBytes = Math.min(payloadBytes, 2048);
        return index + "-" + ProbeSupport.urlEncode(ProbeSupport.uniquePayload(index, retainedBytes));
    }

    private static JettyPushProbeSupport.CacheStats stats(PushSessionCacheFilter filter) throws Exception {
        Map<String, ?> cache = JettyPushProbeSupport.cache(filter);
        return JettyPushProbeSupport.associatedStats(cache);
    }

    private static int get(HttpClient client, int port, String path, String referer) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofMinutes(5))
                .version(HttpClient.Version.HTTP_1_1)
                .GET();
        if (referer != null) {
            request.header("Referer", referer);
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.discarding()).statusCode();
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        PushSessionCacheFilter filter = new PushSessionCacheFilter();
        JettyPushProbeSupport.installOomHandler(() -> stats(filter));
        Server server = JettyPushProbeSupport.startServer(port, filter);

        ProbeSupport.printCommon("jetty-push-session-cache-real-http", requests, payloadBytes, port, profile);
        System.out.println("pushBuilderMode=wrapped_http2_request");
        System.out.println("sessionCookieMode=java_http_client_cookie_manager");
        System.out.flush();

        CookieManager cookieManager = new CookieManager();
        cookieManager.setCookiePolicy(CookiePolicy.ACCEPT_ALL);
        HttpClient client = HttpClient.newBuilder().cookieHandler(cookieManager).build();

        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String primaryPath = "/target-" + pathToken(i, payloadBytes);
                String childPath = "/child-" + pathToken(i + 100_000, payloadBytes);
                int primaryCode = get(client, port, primaryPath, null);
                if (primaryCode != 200) {
                    throw new IllegalStateException("primary GET returned HTTP " + primaryCode);
                }
                int childCode = get(client, port, childPath, "http://127.0.0.1:" + port + primaryPath);
                if (childCode != 200) {
                    throw new IllegalStateException("child GET returned HTTP " + childCode);
                }
                i++;
                if (i % progressEvery == 0) {
                    JettyPushProbeSupport.CacheStats currentStats = stats(filter);
                    JettyPushProbeSupport.printProgress("cache", i, currentStats);
                    if ("oom".equals(profile)) {
                        JettyPushProbeSupport.forceOomIfHeapNearlyFull(i, currentStats);
                    }
                }
            }
            JettyPushProbeSupport.printCompleted(i, stats(filter));
        } catch (OutOfMemoryError oom) {
            JettyPushProbeSupport.printOom(i, stats(filter));
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop();
        }
    }
}
