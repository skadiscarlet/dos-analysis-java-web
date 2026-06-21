package org.example.dos.dynamic;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import io.undertow.Undertow;
import io.undertow.UndertowOptions;
import io.undertow.server.HttpServerExchange;
import io.undertow.server.handlers.BlockingHandler;
import io.undertow.server.handlers.form.FormData;
import io.undertow.server.handlers.form.FormDataParser;
import io.undertow.server.handlers.form.MultiPartParserDefinition;
import io.undertow.util.Headers;
import io.undertow.util.StatusCodes;

public final class UndertowMultipartHttpProbe {
    private static final String BOUNDARY = "----dosboundary";

    private static byte[] multipartBody(int parts, int payloadBytes) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(Math.max(1024, parts * (payloadBytes + 160)));
        for (int i = 0; i < parts; i++) {
            out.write(("--" + BOUNDARY + "\r\n").getBytes(StandardCharsets.ISO_8859_1));
            out.write(("Content-Disposition: form-data; name=\"part" + i + "\"; filename=\"f" + i + ".txt\"\r\n")
                    .getBytes(StandardCharsets.ISO_8859_1));
            out.write("Content-Type: application/octet-stream\r\n\r\n".getBytes(StandardCharsets.ISO_8859_1));
            out.write(ProbeSupport.uniquePayload(i, payloadBytes).getBytes(StandardCharsets.ISO_8859_1));
            out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
        }
        out.write(("--" + BOUNDARY + "--\r\n").getBytes(StandardCharsets.ISO_8859_1));
        return out.toByteArray();
    }

    private static int tempFileCount(Path tempDir) throws IOException {
        if (!Files.isDirectory(tempDir)) {
            return 0;
        }
        try (var files = Files.list(tempDir)) {
            return (int) files.filter(path -> path.getFileName().toString().startsWith("undertow")).count();
        }
    }

    private static void awaitCleanup(Path tempDir) throws Exception {
        for (int i = 0; i < 5; i++) {
            if (tempFileCount(tempDir) == 0) {
                return;
            }
            Thread.sleep(20);
        }
    }

    private static void awaitFinalCleanup(Path tempDir) throws Exception {
        for (int i = 0; i < 50; i++) {
            if (tempFileCount(tempDir) == 0) {
                return;
            }
            Thread.sleep(100);
        }
    }

    private static int multipart(int port, byte[] body) throws Exception {
        return ProbeSupport.http(
                "POST",
                "http://127.0.0.1:" + port + "/upload",
                Map.of("Content-Type", "multipart/form-data; boundary=" + BOUNDARY),
                body);
    }

    public static void main(String[] args) throws Exception {
        int configuredParts = Integer.parseInt(args[0]);
        int requestLimit = configuredParts < 0 ? 128 : configuredParts;
        int parts = configuredParts < 0 ? 64 : configuredParts;
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        Path tempDir = Path.of("target", "undertow-multipart-" + port).toAbsolutePath();
        Files.createDirectories(tempDir);
        MultiPartParserDefinition parserDefinition = new MultiPartParserDefinition(tempDir);
        parserDefinition.setFileSizeThreshold(0);
        AtomicInteger requestsCompleted = new AtomicInteger();
        AtomicInteger materializedParts = new AtomicInteger();
        AtomicInteger multipartFiles = new AtomicInteger();

        ProbeSupport.installOomExitHandler(() -> {
            System.out.println("requestsBeforeOom=" + requestsCompleted.get());
            System.out.println("materializedPartsBeforeOom=" + materializedParts.get());
            System.out.println("multipartFilesBeforeOom=" + multipartFiles.get());
            try {
                System.out.println("tempFilesBeforeOom=" + tempFileCount(tempDir));
            } catch (IOException ignored) {
                System.out.println("tempFilesBeforeOom=unknown");
            }
            System.out.println("oomSignal=uncaught_handler");
        });

        Undertow server = Undertow.builder()
                .addHttpListener(port, "127.0.0.1")
                .setServerOption(UndertowOptions.MAX_PARAMETERS, Math.max(1000, parts + 1))
                .setHandler(new BlockingHandler(exchange -> handle(exchange, parserDefinition, materializedParts, multipartFiles)))
                .build();
        server.start();

        ProbeSupport.printCommon("undertow-multipart-real-http", configuredParts, payloadBytes, port, profile);
        System.out.println("partsPerRequest=" + parts);
        System.out.println("unboundedProfile=" + (configuredParts < 0));
        System.out.println("defaultMaxParameters=1000");
        System.out.println("configuredMaxParameters=" + Math.max(1000, parts + 1));
        System.out.println("fileSizeThreshold=0");
        System.out.println("oomProbeRequestLimit=" + requestLimit);
        System.out.println("tempDir=" + tempDir);
        System.out.flush();

        byte[] body = multipartBody(parts, payloadBytes);
        int i = 0;
        try {
            while (i < requestLimit) {
                int code = multipart(port, body);
                if (code != 200) {
                    System.out.println("verdict=BLOCKED_BOUNDED_OR_REJECTED");
                    System.out.println("blockedHttpStatus=" + code);
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("materializedParts=" + materializedParts.get());
                    System.out.println("multipartFiles=" + multipartFiles.get());
                    return;
                }
                i++;
                requestsCompleted.set(i);
                if (i % progressEvery == 0) {
                    awaitCleanup(tempDir);
                    System.out.println("progress requests=" + i
                            + " materializedParts=" + materializedParts.get()
                            + " multipartFiles=" + multipartFiles.get()
                            + " tempFiles=" + tempFileCount(tempDir)
                            + " cleanupRemovedTempFiles=" + (tempFileCount(tempDir) == 0)
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
                if ("oom".equals(profile) && i >= requestLimit) {
                    awaitFinalCleanup(tempDir);
                    System.out.println("verdict=NOT_VERIFIED_CLEANUP_BOUNDED");
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("materializedParts=" + materializedParts.get());
                    System.out.println("multipartFiles=" + multipartFiles.get());
                    System.out.println("tempFiles=" + tempFileCount(tempDir));
                    System.out.println("cleanupRemovedTempFiles=" + (tempFileCount(tempDir) == 0));
                    System.out.println("notes=stopped after bounded OOM probe without heap OOM; temp-file cleanup is asynchronous");
                    return;
                }
            }
            awaitFinalCleanup(tempDir);
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("materializedParts=" + materializedParts.get());
            System.out.println("multipartFiles=" + multipartFiles.get());
            System.out.println("tempFiles=" + tempFileCount(tempDir));
            System.out.println("cleanupRemovedTempFiles=" + (tempFileCount(tempDir) == 0));
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("materializedPartsBeforeOom=" + materializedParts.get());
            System.out.println("multipartFilesBeforeOom=" + multipartFiles.get());
            System.out.println("tempFilesBeforeOom=" + tempFileCount(tempDir));
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop();
        }
    }

    private static void handle(
            HttpServerExchange exchange,
            MultiPartParserDefinition parserDefinition,
            AtomicInteger materializedParts,
            AtomicInteger multipartFiles) throws Exception {
        FormDataParser parser = parserDefinition.create(exchange);
        if (parser == null) {
            exchange.setStatusCode(StatusCodes.BAD_REQUEST);
            exchange.getResponseSender().send("missing multipart parser");
            return;
        }
        FormData data = parser.parseBlocking();
        int parts = 0;
        int files = 0;
        for (String name : data) {
            var values = data.get(name);
            if (values == null) {
                continue;
            }
            for (FormData.FormValue value : values) {
                parts++;
                if (value.isFileItem()) {
                    files++;
                }
            }
        }
        materializedParts.addAndGet(parts);
        multipartFiles.addAndGet(files);
        exchange.setStatusCode(StatusCodes.OK);
        exchange.getResponseHeaders().put(Headers.CONTENT_TYPE, "text/plain");
        exchange.getResponseSender().send("parts=" + parts + " files=" + files);
    }
}
