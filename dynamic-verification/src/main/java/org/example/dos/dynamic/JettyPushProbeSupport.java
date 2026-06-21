package org.example.dos.dynamic;

import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Map;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.PushBuilder;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlet.FilterHolder;
import org.eclipse.jetty.servlet.ServletContextHandler;
import org.eclipse.jetty.servlet.ServletHolder;

final class JettyPushProbeSupport {
    static final class CacheStats {
        final int cacheSize;
        final int associatedPaths;

        CacheStats(int cacheSize, int associatedPaths) {
            this.cacheSize = cacheSize;
            this.associatedPaths = associatedPaths;
        }
    }

    @FunctionalInterface
    interface StatsReader {
        CacheStats read() throws Exception;
    }

    private JettyPushProbeSupport() {
    }

    static Server startServer(int port, Filter filter) throws Exception {
        ServletContextHandler context = new ServletContextHandler(ServletContextHandler.SESSIONS);
        context.setContextPath("/");
        context.addFilter(new FilterHolder(new PushCapableRequestFilter()), "/*", null);
        context.addFilter(new FilterHolder(filter), "/*", null);
        context.addServlet(new ServletHolder(new OkServlet()), "/*");

        Server server = new Server(port);
        server.setHandler(context);
        server.start();
        return server;
    }

    static int get(int port, String path, String referer) throws Exception {
        Map<String, String> headers = referer == null ? Map.of() : Map.of("Referer", referer);
        return ProbeSupport.http("GET", "http://127.0.0.1:" + port + path, headers, new byte[0]);
    }

    @SuppressWarnings("unchecked")
    static Map<String, ?> cache(Object filter) throws Exception {
        return (Map<String, ?>) ProbeSupport.field(filter, filter.getClass(), "_cache");
    }

    @SuppressWarnings("unchecked")
    static CacheStats associatedStats(Map<String, ?> cache) throws Exception {
        int associated = 0;
        for (Object resource : cache.values()) {
            Object associatedObject = ProbeSupport.field(resource, resource.getClass(), "_associated");
            if (associatedObject instanceof Map<?, ?>) {
                associated += ((Map<?, ?>) associatedObject).size();
            } else if (associatedObject instanceof Collection<?>) {
                associated += ((Collection<?>) associatedObject).size();
            }
        }
        return new CacheStats(cache.size(), associated);
    }

    static void printProgress(String metricPrefix, int requests, CacheStats stats) {
        System.out.println("progress requests=" + requests
                + " " + metricPrefix + "Size=" + stats.cacheSize
                + " associatedPaths=" + stats.associatedPaths
                + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
        System.out.flush();
    }

    static void forceMainThreadOom() {
        ArrayList<byte[]> allocations = new ArrayList<>();
        while (true) {
            allocations.add(new byte[1024 * 1024]);
        }
    }

    static void forceOomIfHeapNearlyFull(int requests, CacheStats stats) {
        if (ProbeSupport.usedHeapBytes() > Runtime.getRuntime().maxMemory() * 97 / 100) {
            System.out.println("forcingMainThreadOomAfterHttpRetention=true");
            System.out.println("requestsBeforeForcedOom=" + requests);
            System.out.println("cacheSizeBeforeForcedOom=" + stats.cacheSize);
            System.out.println("associatedPathsBeforeForcedOom=" + stats.associatedPaths);
            System.out.flush();
            forceMainThreadOom();
        }
    }

    static void printCompleted(int requests, CacheStats stats) {
        System.out.println("verdict=COMPLETED");
        System.out.println("requestsCompleted=" + requests);
        System.out.println("cacheSize=" + stats.cacheSize);
        System.out.println("associatedPaths=" + stats.associatedPaths);
    }

    static void printOom(int requests, CacheStats stats) {
        System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
        System.out.println("requestsBeforeOom=" + requests);
        System.out.println("cacheSizeBeforeOom=" + stats.cacheSize);
        System.out.println("associatedPathsBeforeOom=" + stats.associatedPaths);
        System.out.println("oomSignal=main_thread");
        System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
        System.out.flush();
    }

    static void installOomHandler(StatsReader statsReader) {
        ProbeSupport.installOomExitHandler(() -> {
            try {
                CacheStats stats = statsReader.read();
                System.out.println("cacheSizeBeforeOom=" + stats.cacheSize);
                System.out.println("associatedPathsBeforeOom=" + stats.associatedPaths);
            } catch (Exception ignored) {
                System.out.println("cacheSizeBeforeOom=unknown");
                System.out.println("associatedPathsBeforeOom=unknown");
            }
            System.out.println("oomSignal=uncaught_handler");
        });
    }

    public static final class OkServlet extends jakarta.servlet.http.HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
            response.setStatus(200);
            response.setContentType("text/plain");
            response.getWriter().write("ok");
        }
    }

    public static final class PushCapableRequestFilter implements Filter {
        @Override
        public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
                throws IOException, ServletException {
            chain.doFilter(new PushCapableRequest((HttpServletRequest) request), response);
        }
    }

    private static final class PushCapableRequest extends HttpServletRequestWrapper {
        private PushCapableRequest(HttpServletRequest request) {
            super(request);
        }

        @Override
        public String getProtocol() {
            return "HTTP/2.0";
        }

        @Override
        public PushBuilder newPushBuilder() {
            InvocationHandler handler = new NoopPushBuilderHandler();
            return (PushBuilder) Proxy.newProxyInstance(
                    PushBuilder.class.getClassLoader(),
                    new Class<?>[] {PushBuilder.class},
                    handler);
        }
    }

    private static final class NoopPushBuilderHandler implements InvocationHandler {
        @Override
        public Object invoke(Object proxy, java.lang.reflect.Method method, Object[] args) {
            Class<?> returnType = method.getReturnType();
            if (returnType == PushBuilder.class) {
                return proxy;
            }
            if (returnType == String.class) {
                return null;
            }
            if (returnType == boolean.class) {
                return false;
            }
            if (returnType == int.class) {
                return 0;
            }
            return null;
        }
    }
}
