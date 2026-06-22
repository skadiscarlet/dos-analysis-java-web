package org.example.dos.dynamic;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.context.event.ApplicationEventPublisher;
import io.micronaut.caffeine.cache.Cache;
import io.micronaut.session.DefaultSessionIdGenerator;
import io.micronaut.session.InMemorySession;
import io.micronaut.session.InMemorySessionStore;
import io.micronaut.session.SessionConfiguration;

public final class MicronautInMemorySessionHttpProbe {
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static InMemorySessionStore store;

    private static void send(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static long activeSessions() {
        try {
            @SuppressWarnings("unchecked")
            Cache<String, InMemorySession> sessions =
                    (Cache<String, InMemorySession>) ProbeSupport.field(store, InMemorySessionStore.class, "sessions");
            return sessions.estimatedSize();
        } catch (Exception ignored) {
            return -1;
        }
    }

    private static void reportOom(String signal) {
        System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
        System.out.println("requestsBeforeOom=" + REQUESTS.get());
        System.out.println("activeSessionsBeforeOom=" + activeSessions());
        System.out.println("oomSignal=" + signal);
        System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
        System.out.flush();
    }

    private static HttpServer startEntry(int port, int payloadBytes) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        server.createContext("/session", exchange -> {
            try {
                InMemorySession session = store.newSession();
                session.put("payload", ProbeSupport.uniquePayload(REQUESTS.get(), payloadBytes));
                store.save(session).join();
                int count = REQUESTS.incrementAndGet();
                send(exchange, 200, "session=" + count);
            } catch (OutOfMemoryError oom) {
                reportOom("http_handler");
                System.exit(ProbeSupport.OOM_EXIT_CODE);
            } catch (Throwable throwable) {
                send(exchange, 500, throwable.getClass().getName());
            }
        });
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();
        return server;
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        SessionConfiguration configuration = new SessionConfiguration();
        store = new InMemorySessionStore(new DefaultSessionIdGenerator(), configuration, ApplicationEventPublisher.noOp());
        ProbeSupport.installOomExitHandler(() -> {
            System.out.println("requestsBeforeOom=" + REQUESTS.get());
            System.out.println("activeSessionsBeforeOom=" + activeSessions());
            System.out.println("oomSignal=uncaught_handler");
        });

        HttpServer server = startEntry(port, payloadBytes);
        ProbeSupport.printCommon("micronaut-inmemory-session-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_http_entry_to_micronaut_inmemory_session_store");
        System.out.println("defaultMaxInactiveIntervalMinutes=30");
        System.out.println("maxActiveSessionsConfigured=false");
        System.out.flush();

        int limit = requests < 0 ? Integer.MAX_VALUE : requests;
        int i = 0;
        try {
            while (i < limit) {
                int code = ProbeSupport.http("GET", "http://127.0.0.1:" + port + "/session", Map.of(), new byte[0]);
                if (code != 200) {
                    throw new IllegalStateException("session endpoint returned HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " activeSessions=" + activeSessions()
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
                if ("oom".equals(profile) && i >= limit) {
                    System.out.println("verdict=NOT_VERIFIED_CONFIGURATION_DEPENDENT");
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("activeSessions=" + activeSessions());
                    System.out.println("notes=real HTTP session creation reproduced; run stopped before heap OOM");
                    return;
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("activeSessions=" + activeSessions());
        } catch (OutOfMemoryError oom) {
            reportOom("main_thread");
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop(0);
        }
    }
}
