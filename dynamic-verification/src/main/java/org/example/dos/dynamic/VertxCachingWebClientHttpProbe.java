package org.example.dos.dynamic;

import java.util.HashMap;
import java.util.Map;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.client.CachingWebClient;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.impl.cache.CacheKey;
import io.vertx.ext.web.client.impl.cache.CachedHttpResponse;
import io.vertx.ext.web.client.spi.CacheStore;

public final class VertxCachingWebClientHttpProbe {
    private static final class CountingCacheStore implements CacheStore {
        private final Map<CacheKey, CachedHttpResponse> map = new HashMap<>();

        @Override
        public Future<CachedHttpResponse> get(CacheKey key) {
            return Future.succeededFuture(map.get(key));
        }

        @Override
        public Future<CachedHttpResponse> set(CacheKey key, CachedHttpResponse response) {
            map.put(key, response);
            return Future.succeededFuture(response);
        }

        @Override
        public Future<Void> delete(CacheKey key) {
            map.remove(key);
            return Future.succeededFuture();
        }

        @Override
        public Future<Void> flush() {
            map.clear();
            return Future.succeededFuture();
        }

        int size() {
            return map.size();
        }
    }

    public static void main(String[] args) throws Exception {
        int requests = Integer.parseInt(args[0]);
        int payloadBytes = Integer.parseInt(args[1]);
        int progressEvery = Integer.parseInt(args[2]);
        int port = Integer.parseInt(args[3]);
        String profile = args[4];
        int upstreamPort = port + 1000;

        Vertx vertx = Vertx.vertx();
        CountingCacheStore cacheStore = new CountingCacheStore();
        WebClient cachingClient = CachingWebClient.create(WebClient.create(vertx), cacheStore);
        Router upstream = Router.router(vertx);
        upstream.get("/cache").handler(ctx -> {
            String key = ctx.queryParam("key").isEmpty() ? "missing" : ctx.queryParam("key").get(0);
            ctx.response()
                    .putHeader("Cache-Control", "public, max-age=3600")
                    .putHeader("Content-Type", "text/plain")
                    .end(ProbeSupport.uniquePayload(key.hashCode(), payloadBytes));
        });
        Router entry = Router.router(vertx);
        entry.get("/fetch").handler(ctx -> {
            String key = ctx.queryParam("key").isEmpty() ? "missing" : ctx.queryParam("key").get(0);
            cachingClient.get(upstreamPort, "127.0.0.1", "/cache?key=" + ProbeSupport.urlEncode(key)).send(ar -> {
                if (ar.succeeded()) {
                    ctx.response().end("cacheEntries=" + cacheStore.size());
                } else {
                    ctx.response().setStatusCode(502).end(ar.cause().getClass().getName());
                }
            });
        });
        vertx.createHttpServer().requestHandler(upstream).listen(upstreamPort, "127.0.0.1").toCompletionStage().toCompletableFuture().get();
        vertx.createHttpServer().requestHandler(entry).listen(port, "127.0.0.1").toCompletionStage().toCompletableFuture().get();

        ProbeSupport.installOomExitHandler(() -> {
            System.out.println("requestsBeforeOom=unknown");
            System.out.println("cacheEntriesBeforeOom=" + cacheStore.size());
            System.out.println("oomSignal=uncaught_handler");
        });

        ProbeSupport.printCommon("vertx-caching-webclient-real-http", requests, payloadBytes, port, profile);
        System.out.println("harnessMode=real_http_entry_to_vertx_caching_webclient");
        System.out.println("cacheStoreCapacityFound=false");
        System.out.println("upstreamCacheControl=public,max-age=3600");
        System.out.flush();

        int limit = requests < 0 ? Integer.MAX_VALUE : requests;
        int i = 0;
        try {
            while (i < limit) {
                int code = ProbeSupport.http(
                        "GET",
                        "http://127.0.0.1:" + port + "/fetch?key=k" + i,
                        Map.of(),
                        new byte[0]);
                if (code != 200) {
                    throw new IllegalStateException("entry endpoint returned HTTP " + code);
                }
                i++;
                if (i % progressEvery == 0) {
                    System.out.println("progress requests=" + i
                            + " cacheEntries=" + cacheStore.size()
                            + " usedHeapBytes=" + ProbeSupport.usedHeapBytes());
                    System.out.flush();
                }
                if ("oom".equals(profile) && i >= limit) {
                    System.out.println("verdict=NOT_VERIFIED_CONFIGURATION_DEPENDENT");
                    System.out.println("requestsCompleted=" + i);
                    System.out.println("cacheEntries=" + cacheStore.size());
                    System.out.println("notes=app-controlled cache key path reproduced; run stopped before heap OOM");
                    return;
                }
            }
            System.out.println("verdict=COMPLETED");
            System.out.println("requestsCompleted=" + i);
            System.out.println("cacheEntries=" + cacheStore.size());
        } catch (OutOfMemoryError oom) {
            System.out.println("verdict=CONFIRMED_HEAP_OOM_REAL_HTTP");
            System.out.println("requestsBeforeOom=" + i);
            System.out.println("cacheEntriesBeforeOom=" + cacheStore.size());
            System.out.println("oomSignal=main_thread");
            System.out.println("usedHeapBytesAtOom=" + ProbeSupport.usedHeapBytes());
            System.out.flush();
            System.exit(ProbeSupport.OOM_EXIT_CODE);
        } finally {
            vertx.close().toCompletionStage().toCompletableFuture().get();
        }
    }
}
