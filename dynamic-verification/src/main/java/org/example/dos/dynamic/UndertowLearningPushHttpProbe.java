package org.example.dos.dynamic;

import java.util.Map;

import io.undertow.Undertow;
import io.undertow.server.HttpHandler;
import io.undertow.server.HttpServerExchange;
import io.undertow.server.handlers.LearningPushHandler;
import io.undertow.server.handlers.cache.LRUCache;

public final class UndertowLearningPushHttpProbe {
    @SuppressWarnings("unchecked")
    private static LRUCache<String, Map<String, ?>> cache(LearningPushHandler handler) throws Exception {
        return (LRUCache<String, Map<String, ?>>) ProbeSupport.field(handler, LearningPushHandler.class, "cache");
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        String referer = "http://127.0.0.1:" + port + "/page";

        LearningPushHandler learning = new LearningPushHandler(new HttpHandler() {
            @Override
            public void handleRequest(HttpServerExchange exchange) {
                exchange.setStatusCode(200);
                exchange.getResponseSender().send("ok");
            }
        });
        ProbeSupport.installOomExitHandler(() -> {
            try {
                Map<String, ?> inner = cache(learning).get(referer);
                System.out.println("innerResourceEntriesBeforeOom=" + (inner == null ? 0 : inner.size()));
            } catch (Exception ignored) {
                System.out.println("innerResourceEntriesBeforeOom=unknown");
            }
        });

        Undertow server = Undertow.builder()
                .addHttpListener(port, "127.0.0.1")
                .setHandler(learning)
                .build();
        server.start();

        ProbeSupport.printCommon("undertow-learning-push-real-http", requests, payloadBytes, port, profile);
        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String query = payloadBytes > 0 ? "?q=" + ProbeSupport.urlEncode(ProbeSupport.uniquePayload(i, payloadBytes)) : "?q=" + i;
                int code = ProbeSupport.http(
                        "GET",
                        "http://127.0.0.1:" + port + "/asset/" + i + ".js" + query,
                        Map.of("Referer", referer, "Accept", "application/javascript"),
                        new byte[0]);
                if (code != 200) {
                    throw new IllegalStateException("unexpected HTTP status " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    Map<String, ?> inner = cache(learning).get(referer);
                    System.out.println("progress requests=" + i
                            + " innerResourceEntries=" + (inner == null ? 0 : inner.size())
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            Map<String, ?> inner = cache(learning).get(referer);
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("innerResourceEntries=" + (inner == null ? 0 : inner.size()));
        } catch (OutOfMemoryError oom) {
            Map<String, ?> inner = cache(learning).get(referer);
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("innerResourceEntriesBeforeOom=" + (inner == null ? 0 : inner.size()));
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop();
        }
    }
}
