package io.undertow.server.handlers.proxy.mod_cluster;

import java.lang.reflect.Field;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import io.undertow.Undertow;
import io.undertow.client.UndertowClient;
import io.undertow.server.HttpHandler;
import io.undertow.server.HttpServerExchange;
import org.example.dos.dynamic.ProbeSupport;
import org.xnio.OptionMap;
import org.xnio.Xnio;
import org.xnio.XnioWorker;

public final class UndertowModClusterHttpProbe {
    @SuppressWarnings("unchecked")
    private static int mapSize(ModClusterContainer container, String fieldName) throws Exception {
        Field field = ModClusterContainer.class.getDeclaredField(fieldName);
        field.setAccessible(true);
        return ((Map<?, ?>) field.get(container)).size();
    }

    private static String enc(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static String form(int index, int payloadBytes) {
        String balancer = ProbeSupport.uniquePayload(index, payloadBytes);
        String alias = ProbeSupport.uniquePayload(index + 100_000, payloadBytes) + ".example";
        return "Balancer=" + enc(balancer)
                + "&JVMRoute=" + enc("route-" + index)
                + "&Host=127.0.0.1"
                + "&Port=" + (8000 + (index % 1000))
                + "&Type=http"
                + "&Context=" + enc("/ctx-" + index)
                + "&Alias=" + enc(alias);
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        XnioWorker worker = Xnio.getInstance().createWorker(OptionMap.EMPTY);
        ModCluster modCluster = ModCluster.builder(worker, UndertowClient.getInstance()).build();
        ModClusterContainer container = modCluster.getContainer();
        MCMPConfig config = MCMPConfig.builder().setManagementHost("127.0.0.1").setManagementPort(port).build();
        HttpHandler mcmp = config.create(modCluster, new HttpHandler() {
            @Override
            public void handleRequest(HttpServerExchange exchange) {
                exchange.setStatusCode(404);
            }
        });

        ProbeSupport.installOomExitHandler(() -> {
            try {
                System.out.println("nodesBeforeOom=" + mapSize(container, "nodes"));
                System.out.println("balancersBeforeOom=" + mapSize(container, "balancers"));
                System.out.println("hostsBeforeOom=" + mapSize(container, "hosts"));
            } catch (Exception ignored) {
                System.out.println("nodesBeforeOom=unknown");
                System.out.println("balancersBeforeOom=unknown");
                System.out.println("hostsBeforeOom=unknown");
            }
        });

        Undertow server = Undertow.builder()
                .addHttpListener(port, "127.0.0.1")
                .setHandler(mcmp)
                .build();
        server.start();

        ProbeSupport.printCommon("undertow-mod-cluster-real-http", requests, payloadBytes, port, profile);
        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                byte[] body = form(i, payloadBytes).getBytes(StandardCharsets.UTF_8);
                int code = ProbeSupport.http(
                        "CONFIG",
                        "http://127.0.0.1:" + port + "/",
                        Map.of("Content-Type", "application/x-www-form-urlencoded"),
                        body);
                if (code >= 500 && ProbeSupport.usedHeapBytes() > Runtime.getRuntime().maxMemory() * 90 / 100) {
                    System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
                    System.out.println("requestsBeforeOom=" + i);
                    System.out.println("nodesBeforeOom=" + mapSize(container, "nodes"));
                    System.out.println("balancersBeforeOom=" + mapSize(container, "balancers"));
                    System.out.println("hostsBeforeOom=" + mapSize(container, "hosts"));
                    System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                    System.exit(ProbeSupport.OOM_EXIT_CODE);
                }
                if (code != 200) {
                    throw new IllegalStateException("CONFIG returned HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " nodes=" + mapSize(container, "nodes")
                            + " balancers=" + mapSize(container, "balancers")
                            + " hosts=" + mapSize(container, "hosts")
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("nodes=" + mapSize(container, "nodes"));
            System.out.println("balancers=" + mapSize(container, "balancers"));
            System.out.println("hosts=" + mapSize(container, "hosts"));
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("nodesBeforeOom=" + mapSize(container, "nodes"));
            System.out.println("balancersBeforeOom=" + mapSize(container, "balancers"));
            System.out.println("hostsBeforeOom=" + mapSize(container, "hosts"));
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop();
            worker.shutdownNow();
        }
    }
}
