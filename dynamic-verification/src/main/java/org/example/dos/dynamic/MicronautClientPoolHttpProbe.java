package org.example.dos.dynamic;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.client.DefaultHttpClientConfiguration;
import io.micronaut.http.client.HttpClient;
import io.micronaut.http.client.HttpClientConfiguration;

public final class MicronautClientPoolHttpProbe {
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static HttpClient client;

    private static String hostToken(int index, int payloadBytes) {
        StringBuilder builder = new StringBuilder(Math.max(16, payloadBytes));
        builder.append("mn").append(index).append("-");
        while (builder.length() < payloadBytes) {
            builder.append((char) ('a' + (index % 26)));
        }
        builder.append(".example.invalid");
        return builder.toString();
    }

    private static void send(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static HttpServer startEntry(int port, int upstreamPort) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        server.createContext("/fetch", exchange -> {
            String query = exchange.getRequestURI().getRawQuery();
            String host = query == null ? "missing.example.invalid" : query.replace("host=", "");
            try {
                client.toBlocking().exchange(HttpRequest.GET("http://" + host + ":" + upstreamPort + "/resource"), String.class);
                REQUESTS.incrementAndGet();
                send(exchange, 200, "ok");
            } catch (OutOfMemoryError oom) {
                throw oom;
            } catch (Throwable throwable) {
                send(exchange, 502, throwable.getClass().getName());
            }
        });
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();
        return server;
    }

    private static int poolKeys() {
        try {
            Object connectionManager = ProbeSupport.field(client, client.getClass(), "connectionManager");
            Object poolMap = ProbeSupport.field(connectionManager, connectionManager.getClass(), "poolMap");
            if (poolMap instanceof Iterable<?>) {
                int count = 0;
                for (Object ignored : (Iterable<?>) poolMap) {
                    count++;
                }
                return count;
            }
        } catch (Exception ignored) {
            return -1;
        }
        return 0;
    }

    private static final class LocalConnectProxy implements AutoCloseable {
        private final ServerSocket serverSocket;
        private final ExecutorService executor = Executors.newCachedThreadPool();
        private final AtomicBoolean running = new AtomicBoolean(true);

        private LocalConnectProxy(int port) throws IOException {
            this.serverSocket = new ServerSocket();
            this.serverSocket.bind(new InetSocketAddress("127.0.0.1", port));
            this.executor.submit(this::acceptLoop);
        }

        private void acceptLoop() {
            while (running.get()) {
                try {
                    Socket socket = serverSocket.accept();
                    executor.submit(() -> handle(socket));
                } catch (IOException exception) {
                    if (running.get()) {
                        exception.printStackTrace(System.out);
                    }
                }
            }
        }

        private void handle(Socket socket) {
            try (Socket closeable = socket) {
                closeable.setSoTimeout(300000);
                InputStream in = closeable.getInputStream();
                OutputStream out = closeable.getOutputStream();
                String firstLine = readHeaders(in);
                if (firstLine == null) {
                    return;
                }
                if (firstLine.startsWith("CONNECT ")) {
                    out.write("HTTP/1.1 200 Connection Established\r\n\r\n".getBytes(StandardCharsets.ISO_8859_1));
                    out.flush();
                    readHeaders(in);
                }
                byte[] body = "ok".getBytes(StandardCharsets.ISO_8859_1);
                out.write(("HTTP/1.1 200 OK\r\nContent-Length: " + body.length
                        + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
                out.write(body);
                out.flush();
            } catch (IOException exception) {
                if (running.get()) {
                    exception.printStackTrace(System.out);
                }
            }
        }

        private static String readHeaders(InputStream in) throws IOException {
            String firstLine = readLine(in);
            if (firstLine == null) {
                return null;
            }
            String line;
            while ((line = readLine(in)) != null && !line.isEmpty()) {
                // drain headers
            }
            return firstLine;
        }

        private static String readLine(InputStream in) throws IOException {
            StringBuilder builder = new StringBuilder();
            int value;
            boolean readAny = false;
            while ((value = in.read()) != -1) {
                readAny = true;
                if (value == '\n') {
                    break;
                }
                if (value != '\r') {
                    builder.append((char) value);
                }
            }
            if (!readAny && builder.length() == 0) {
                return null;
            }
            return builder.toString();
        }

        @Override
        public void close() throws IOException {
            running.set(false);
            serverSocket.close();
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        int proxyPort = port + 1000;

        HttpClientConfiguration configuration = new DefaultHttpClientConfiguration();
        configuration.getConnectionPoolConfiguration().setEnabled(true);
        configuration.getConnectionPoolConfiguration().setMaxConnections(1);
        configuration.setProxyType(Proxy.Type.HTTP);
        configuration.setProxyAddress(new InetSocketAddress("127.0.0.1", proxyPort));
        client = HttpClient.create(null, configuration);

        ProbeSupport.installOomExitHandler(() -> {
            System.out.println("requestsBeforeOom=" + REQUESTS.get());
            System.out.println("poolKeysBeforeOom=" + poolKeys());
            System.out.println("oomSignal=uncaught_handler");
        });

        int i = 0;
        HttpServer entry = null;
        try (LocalConnectProxy proxy = new LocalConnectProxy(proxyPort)) {
            entry = startEntry(port, proxyPort);
            ProbeSupport.printCommon("micronaut-client-pool-real-http", requests, payloadBytes, port, profile);
            System.out.println("harnessMode=real_http_entry_to_micronaut_httpclient_pool_via_local_connect_proxy");
            System.out.println("poolEnabled=true");
            System.out.println("maxConnectionsPerPool=1");
            System.out.println("distinctPoolKeyCapFound=false");
            System.out.flush();

            int limit = requests < 0 ? Integer.MAX_VALUE : requests;
            while (i < limit) {
                int code = ProbeSupport.http(
                        "GET",
                        "http://127.0.0.1:" + port + "/fetch?host=" + hostToken(i, payloadBytes),
                        Map.of(),
                        new byte[0]);
                if (code != 200) {
                    throw new IllegalStateException("entry endpoint returned HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " poolKeys=" + poolKeys()
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
                if ("oom".equals(profile) && i >= limit) {
                    System.out.println("verdict=NOT_VERIFIED_CONFIGURATION_DEPENDENT");
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("poolKeys=" + poolKeys());
                    System.out.println("notes=app-controlled outbound host and pooling reproduced; run stopped before heap OOM");
                    return;
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("poolKeys=" + poolKeys());
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("poolKeysBeforeOom=" + poolKeys());
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            if (entry != null) {
                entry.stop(0);
            }
            client.close();
        }
    }
}
