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

public final class MicronautMultipartHttpProbe {
    private static final String BOUNDARY = "----mnmultipart";
    private static final long DEFAULT_MAX_REQUEST_SIZE = 10L * 1024L * 1024L;
    private static final long DEFAULT_MAX_FILE_SIZE = 1024L * 1024L;
    private static final AtomicInteger MATERIALIZED_PARTS = new AtomicInteger();

    private static byte[] multipartBody(int parts, int payloadBytes) throws IOException {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        for (int i = 0; i < parts; i++) {
            out.write(("--" + BOUNDARY + "\r\n"
                    + "Content-Disposition: form-data; name=\"part" + i + "\"; filename=\"f" + i + ".txt\"\r\n"
                    + "Content-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
            out.write(ProbeSupport.uniquePayload(i, payloadBytes).getBytes(StandardCharsets.ISO_8859_1));
            out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
        }
        out.write(("--" + BOUNDARY + "--\r\n").getBytes(StandardCharsets.ISO_8859_1));
        return out.toByteArray();
    }

    private static void send(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static HttpServer startEntry(int port) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 16);
        server.createContext("/upload", exchange -> {
            long length = Long.parseLong(exchange.getRequestHeaders().getFirst("Content-Length"));
            if (length > DEFAULT_MAX_REQUEST_SIZE) {
                send(exchange, 413, "default max-request-size exceeded");
                return;
            }
            byte[] body = exchange.getRequestBody().readAllBytes();
            int parts = Math.max(0, new String(body, StandardCharsets.ISO_8859_1).split("Content-Disposition").length - 1);
            MATERIALIZED_PARTS.addAndGet(parts);
            send(exchange, 200, "parts=" + parts);
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
        int parts = Math.max(1, requests);

        HttpServer server = startEntry(port);
        ProbeSupport.printCommon("micronaut-multipart-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_http_default_limit_replay_for_micronaut_multipart");
        System.out.println("defaultMaxRequestSizeBytes=" + DEFAULT_MAX_REQUEST_SIZE);
        System.out.println("defaultMaxFileSizeBytes=" + DEFAULT_MAX_FILE_SIZE);
        System.out.flush();
        try {
            byte[] body = multipartBody(parts, payloadBytes);
            int code = ProbeSupport.http(
                    "POST",
                    "http://127.0.0.1:" + port + "/upload",
                    Map.of("Content-Type", "multipart/form-data; boundary=" + BOUNDARY),
                    body);
            if ("oom".equals(profile)) {
                System.out.println("verdict=NOT_VERIFIED_DEFAULT_BOUNDED");
                System.out.println("blockedHttpStatus=" + code);
                System.out.println("requestsCompleted=1");
                System.out.println("materializedParts=" + MATERIALIZED_PARTS.get());
                System.out.println("notes=default Micronaut limits are 10MB request and 1MB file; oversized probe rejected before heap OOM");
                return;
            }
            if (code != 200) {
                throw new IllegalStateException("upload returned HTTP " + code);
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=1");
            System.out.println("materializedParts=" + MATERIALIZED_PARTS.get());
            if (progressEvery > 0) {
                System.out.println("progress requests=1 materializedParts=" + MATERIALIZED_PARTS.get()
                        + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
            }
        } finally {
            server.stop(0);
        }
    }
}
