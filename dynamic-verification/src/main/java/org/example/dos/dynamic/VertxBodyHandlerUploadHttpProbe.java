package org.example.dos.dynamic;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.handler.BodyHandler;

public final class VertxBodyHandlerUploadHttpProbe {
    private static final String BOUNDARY = "----vertxupload";

    private static void writeMultipart(OutputStream out, int index, int payloadBytes) throws IOException {
        out.write(("--" + BOUNDARY + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; filename=\"f" + index + ".txt\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
        out.write(ProbeSupport.uniquePayload(index, payloadBytes).getBytes(StandardCharsets.ISO_8859_1));
        out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
        out.write(("--" + BOUNDARY + "--\r\n").getBytes(StandardCharsets.ISO_8859_1));
    }

    private static int upload(int port, int index, int payloadBytes) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:" + port + "/upload").openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(300000);
        connection.setDoOutput(true);
        connection.setChunkedStreamingMode(8192);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + BOUNDARY);
        try (OutputStream out = connection.getOutputStream()) {
            writeMultipart(out, index, payloadBytes);
        }
        int code = connection.getResponseCode();
        if (connection.getErrorStream() != null) {
            connection.getErrorStream().close();
        } else if (connection.getInputStream() != null) {
            connection.getInputStream().close();
        }
        return code;
    }

    private static long uploadFiles(Path uploadDir) throws IOException {
        if (!Files.isDirectory(uploadDir)) {
            return 0;
        }
        try (var stream = Files.list(uploadDir)) {
            return stream.filter(Files::isRegularFile).count();
        }
    }

    private static long uploadBytes(Path uploadDir) throws IOException {
        if (!Files.isDirectory(uploadDir)) {
            return 0;
        }
        try (var stream = Files.list(uploadDir)) {
            return stream.filter(Files::isRegularFile).mapToLong(path -> {
                try {
                    return Files.size(path);
                } catch (IOException ignored) {
                    return 0;
                }
            }).sum();
        }
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        Path uploadDir = Path.of("target", "vertx-bodyhandler-uploads-" + port).toAbsolutePath();
        Files.createDirectories(uploadDir);

        Vertx vertx = Vertx.vertx();
        Router router = Router.router(vertx);
        router.post("/upload").handler(BodyHandler.create(uploadDir.toString()));
        router.post("/upload").handler(ctx -> ctx.response().end("files=" + ctx.fileUploads().size()));
        vertx.createHttpServer().requestHandler(router).listen(port, "127.0.0.1").toCompletionStage().toCompletableFuture().get();

        ProbeSupport.printCommon("vertx-bodyhandler-upload-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_vertx_http_bodyhandler_default_success_path");
        System.out.println("deleteUploadedFilesOnEndDefault=false");
        System.out.println("defaultBodyLimitBytes=10485760");
        System.out.println("uploadDir=" + uploadDir);
        System.out.flush();

        int i = 0;
        try {
            while (i < requests) {
                int code = upload(port, i, payloadBytes);
                if (code != 200) {
                    throw new IllegalStateException("upload returned HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " uploadFiles=" + uploadFiles(uploadDir)
                            + " uploadBytes=" + uploadBytes(uploadDir)
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            if ("oom".equals(profile)) {
                System.out.println("verdict=NOT_VERIFIED_DISK_ONLY");
                System.out.println("requestsCompleted=" + i);
                System.out.println("uploadFiles=" + uploadFiles(uploadDir));
                System.out.println("uploadBytes=" + uploadBytes(uploadDir));
                System.out.println("notes=real HTTP uploads persist on disk, but this probe did not trigger service heap OOM");
            } else {
                System.out.println("verdict=COMPLETED");
                System.out.println("requestsCompleted=" + i);
                System.out.println("uploadFiles=" + uploadFiles(uploadDir));
                System.out.println("uploadBytes=" + uploadBytes(uploadDir));
            }
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("uploadFilesBeforeOom=" + uploadFiles(uploadDir));
            System.out.println("uploadBytesBeforeOom=" + uploadBytes(uploadDir));
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            vertx.close().toCompletionStage().toCompletableFuture().get();
        }
    }
}
