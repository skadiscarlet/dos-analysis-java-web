package org.example.dos.dynamic;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.lang.reflect.Field;
import java.net.URLEncoder;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;

public final class ProbeSupport {
    public static final int OOM_EXIT_CODE = 100;

    private ProbeSupport() {
    }

    public static String uniquePayload(int index, int payloadBytes) {
        byte[] bytes = new byte[payloadBytes];
        Arrays.fill(bytes, (byte) ('a' + (index % 26)));
        byte[] suffix = (":" + index).getBytes(StandardCharsets.ISO_8859_1);
        System.arraycopy(suffix, 0, bytes, Math.max(0, payloadBytes - suffix.length), Math.min(suffix.length, payloadBytes));
        return new String(bytes, StandardCharsets.ISO_8859_1);
    }

    public static String urlEncode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public static long usedHeapBytes() {
        return Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
    }

    public static void printCommon(String candidate, int requests, int payloadBytes, int port, String profile) {
        System.out.println("candidate=" + candidate);
        System.out.println("maxHeapBytes=" + Runtime.getRuntime().maxMemory());
        System.out.println("requests=" + requests);
        System.out.println("payloadBytes=" + payloadBytes);
        System.out.println("port=" + port);
        System.out.println("profile=" + profile);
        System.out.flush();
    }

    public static int http(String method, String url, Map<String, String> headers, byte[] body) throws Exception {
        if ("GET".equals(method) || "POST".equals(method)) {
            return urlConnectionHttp(method, url, headers, body);
        }
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofMinutes(5))
                .version(HttpClient.Version.HTTP_1_1)
                .method(method, HttpRequest.BodyPublishers.ofByteArray(body));
        for (Map.Entry<String, String> header : headers.entrySet()) {
            request.header(header.getKey(), header.getValue());
        }
        return HttpClient.newHttpClient().send(request.build(), HttpResponse.BodyHandlers.discarding()).statusCode();
    }

    private static int urlConnectionHttp(String method, String url, Map<String, String> headers, byte[] body) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(300000);
        for (Map.Entry<String, String> header : headers.entrySet()) {
            connection.setRequestProperty(header.getKey(), header.getValue());
        }
        if (body.length > 0) {
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(body);
            }
        }
        int code = connection.getResponseCode();
        InputStream in = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
        if (in != null) {
            try (InputStream closeable = in) {
                byte[] buffer = new byte[8192];
                while (closeable.read(buffer) != -1) {
                    // drain response body
                }
            }
        }
        return code;
    }

    public static void installOomExitHandler(Runnable reporter) {
        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            Throwable current = throwable;
            while (current != null) {
                if (current instanceof OutOfMemoryError) {
                    System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
                    reporter.run();
                    System.out.println("usedHeapBytesAtOom=" + usedHeapBytes());
                    System.out.flush();
                    System.exit(OOM_EXIT_CODE);
                }
                current = current.getCause();
            }
            throwable.printStackTrace(System.out);
            System.out.flush();
        });
    }

    public static Object field(Object target, Class<?> owner, String fieldName) throws Exception {
        Field field = owner.getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(target);
    }

    public static Object staticField(Class<?> owner, String fieldName) throws Exception {
        Field field = owner.getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(null);
    }
}
