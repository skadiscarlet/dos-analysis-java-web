package org.example.dos.dynamic;

import java.util.Map;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlets.PushCacheFilter;

public final class JettyPushCacheFilterHttpProbe {
    private static String pathToken(int index, int payloadBytes) {
        int retainedBytes = Math.min(payloadBytes, 2048);
        return index + "-" + ProbeSupport.urlEncode(ProbeSupport.uniquePayload(index, retainedBytes));
    }

    private static JettyPushProbeSupport.CacheStats stats(PushCacheFilter filter) throws Exception {
        Map<String, ?> cache = JettyPushProbeSupport.cache(filter);
        return JettyPushProbeSupport.associatedStats(cache);
    }

    private static int maxAssociations(PushCacheFilter filter) throws Exception {
        return (Integer) ProbeSupport.field(filter, PushCacheFilter.class, "_maxAssociations");
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        PushCacheFilter filter = new PushCacheFilter();
        JettyPushProbeSupport.installOomHandler(() -> stats(filter));
        Server server = JettyPushProbeSupport.startServer(port, filter);

        ProbeSupport.printCommon("jetty-push-cache-filter-real-http", requests, payloadBytes, port, profile);
        System.out.println("pushBuilderMode=wrapped_http2_request");
        System.out.println("maxAssociations=" + maxAssociations(filter));
        System.out.flush();

        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String primaryPath = "/primary-" + pathToken(i, payloadBytes);
                String childPath = "/asset-" + pathToken(i + 100_000, payloadBytes);
                int primaryCode = JettyPushProbeSupport.get(port, primaryPath, null);
                if (primaryCode != 200) {
                    throw new IllegalStateException("primary GET returned HTTP " + primaryCode);
                }
                int childCode = JettyPushProbeSupport.get(port, childPath, "http://127.0.0.1:" + port + primaryPath);
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
