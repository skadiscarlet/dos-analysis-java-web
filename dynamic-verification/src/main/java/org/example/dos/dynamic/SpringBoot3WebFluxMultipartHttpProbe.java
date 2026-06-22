package org.example.dos.dynamic;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.Part;
import org.springframework.http.server.reactive.ReactorHttpHandlerAdapter;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

import static org.springframework.web.reactive.function.server.RequestPredicates.POST;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

public final class SpringBoot3WebFluxMultipartHttpProbe {
    private static final String BOUNDARY = "----sb3boundary";
    private static final AtomicInteger MATERIALIZED_PARTS = new AtomicInteger();

    private static void writeMultipart(OutputStream out, int parts, int payloadBytes) throws IOException {
        byte[] payload = new byte[payloadBytes];
        for (int i = 0; i < parts; i++) {
            out.write(("--" + BOUNDARY + "\r\n"
                    + "Content-Disposition: form-data; name=\"f" + i + "\"; filename=\"f" + i + ".txt\"\r\n"
                    + "Content-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
            for (int j = 0; j < payload.length; j++) {
                payload[j] = (byte) ('a' + (i % 26));
            }
            out.write(payload);
            out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
        }
        out.write(("--" + BOUNDARY + "--\r\n").getBytes(StandardCharsets.ISO_8859_1));
    }

    private static int postMultipart(int port, int parts, int payloadBytes) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:" + port + "/upload").openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(300000);
        connection.setDoOutput(true);
        connection.setChunkedStreamingMode(8192);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + BOUNDARY);
        try (OutputStream out = connection.getOutputStream()) {
            writeMultipart(out, parts, payloadBytes);
        }
        int code = connection.getResponseCode();
        if (connection.getErrorStream() != null) {
            connection.getErrorStream().close();
        } else if (connection.getInputStream() != null) {
            connection.getInputStream().close();
        }
        return code;
    }

    public static void main(String[] args) throws Exception {
        int parts = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        var router = route(POST("/upload"), request -> request.multipartData().flatMap(map -> {
            int count = 0;
            for (Map.Entry<String, java.util.List<Part>> entry : map.entrySet()) {
                count += entry.getValue().size();
            }
            MATERIALIZED_PARTS.set(count);
            return ServerResponse.ok().contentType(MediaType.TEXT_PLAIN).bodyValue("parts=" + count);
        }));
        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(port)
                .handle(new ReactorHttpHandlerAdapter(RouterFunctions.toHttpHandler(router)))
                .bindNow();

        ProbeSupport.printCommon("spring-boot-3-webflux-multipart-real-http", parts, payloadBytes, port, profile);
        System.out.println("harnessMode=real_http_spring_webflux_multipart_reader");
        System.out.println("bootDefaultMaxParts=-1");
        System.out.println("bootDefaultMaxDiskUsagePerPart=-1");
        System.out.flush();

        try {
            int code = postMultipart(port, parts, payloadBytes);
            if (code != 200) {
                if ("oom".equals(profile)) {
                    System.out.println("verdict=NOT_VERIFIED_DEFAULT_BOUNDED");
                    System.out.println("blockedHttpStatus=" + code);
                    System.out.println("materializedParts=" + MATERIALIZED_PARTS.get());
                    System.out.println("notes=Spring WebFlux runtime rejected or failed request before heap OOM");
                    return;
                }
                throw new IllegalStateException("upload returned HTTP " + code);
            }
            if ("oom".equals(profile)) {
                System.out.println("verdict=NOT_VERIFIED_REQUEST_LOCAL");
                System.out.println("requestsCompleted=1");
                System.out.println("materializedParts=" + MATERIALIZED_PARTS.get());
                System.out.println("notes=multipart request completed without retained heap OOM; risk remains endpoint and deployment dependent");
            } else {
                System.out.println("verdict=COMPLETED");
                System.out.println("requestsCompleted=1");
                System.out.println("materializedParts=" + MATERIALIZED_PARTS.get());
            }
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=1");
            System.out.println("materializedPartsBeforeOom=" + MATERIALIZED_PARTS.get());
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.disposeNow();
        }
    }
}
