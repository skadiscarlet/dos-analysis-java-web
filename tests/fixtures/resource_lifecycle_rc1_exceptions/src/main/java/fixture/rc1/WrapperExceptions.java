package fixture.rc1;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.RejectedExecutionException;

public final class WrapperExceptions {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy());
    private static Resource shared;

    public static void noCleanup() {
        Resource resource = new Resource();
        wrapper(resource);
    }

    public static void callerFinallyCleanup() {
        Resource resource = null;
        try {
            resource = new Resource();
            wrapper(resource);
        } finally {
            resource.close();
        }
    }

    public static void callerCatchHolder() {
        Resource resource = new Resource();
        try {
            wrapper(resource);
        } catch (RejectedExecutionException rejected) {
            shared = resource;
        }
    }

    public static void extraHolder() {
        Resource resource = new Resource();
        shared = resource;
        wrapper(resource);
    }

    private static void wrapper(Resource resource) {
        EXECUTOR.execute(() -> {
            try {
                return;
            } finally {
                resource.close();
            }
        });
    }

    private static final class Resource implements AutoCloseable {
        @Override public void close() { }
    }
}
