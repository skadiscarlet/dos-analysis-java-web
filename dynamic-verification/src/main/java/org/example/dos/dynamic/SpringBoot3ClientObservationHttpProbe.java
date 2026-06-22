package org.example.dos.dynamic;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

public final class SpringBoot3ClientObservationHttpProbe {
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static MeterRegistry meterRegistry;

    private static String hostToken(int index, int payloadBytes) {
        StringBuilder builder = new StringBuilder(Math.max(16, payloadBytes));
        builder.append("h").append(index).append("-");
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

    private static HttpServer startProxy(int port) throws IOException {
        HttpServer proxy = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        proxy.createContext("/", exchange -> send(exchange, 200, "ok"));
        proxy.setExecutor(Executors.newCachedThreadPool());
        proxy.start();
        return proxy;
    }

    private static HttpServer startEntry(int port, RestTemplate restTemplate, int proxyPort) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        server.createContext("/fetch", exchange -> {
            String query = exchange.getRequestURI().getRawQuery();
            String host = query == null ? "missing.example.invalid" : query.replace("host=", "");
            try {
                restTemplate.getForEntity("http://" + host + "/resource", String.class);
                REQUESTS.incrementAndGet();
                send(exchange, 200, "proxyPort=" + proxyPort);
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

    private static int meterCount() {
        return meterRegistry == null ? 0 : meterRegistry.getMeters().size();
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        int proxyPort = port + 1000;

        meterRegistry = new SimpleMeterRegistry();
        ObservationRegistry observationRegistry = ObservationRegistry.create();
        observationRegistry.observationConfig().observationHandler(new DefaultMeterObservationHandler(meterRegistry));
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setProxy(new Proxy(Proxy.Type.HTTP, new InetSocketAddress("127.0.0.1", proxyPort)));
        RestTemplate restTemplate = new RestTemplate(requestFactory);
        restTemplate.setObservationRegistry(observationRegistry);

        ProbeSupport.installOomExitHandler(() -> {
            System.out.println("requestsBeforeOom=" + REQUESTS.get());
            System.out.println("meterCountBeforeOom=" + meterCount());
            System.out.println("oomSignal=uncaught_handler");
        });

        HttpServer proxy = startProxy(proxyPort);
        HttpServer server = startEntry(port, restTemplate, proxyPort);
        ProbeSupport.printCommon("spring-boot-3-client-observation-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_http_entry_to_resttemplate_observation_via_local_proxy");
        System.out.println("bootDefaultUriTagCap=100");
        System.out.println("clientNameCapFound=false");
        System.out.flush();

        int limit = requests < 0 ? Integer.MAX_VALUE : requests;
        int i = 0;
        try {
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
                            + " meterCount=" + meterCount()
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
                if ("oom".equals(profile) && i >= limit) {
                    System.out.println("verdict=NOT_VERIFIED_CONFIGURATION_DEPENDENT");
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("meterCount=" + meterCount());
                    System.out.println("notes=app-controlled outbound host path reproduced; run stopped before heap OOM");
                    return;
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("meterCount=" + meterCount());
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("meterCountBeforeOom=" + meterCount());
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop(0);
            proxy.stop(0);
        }
    }
}
