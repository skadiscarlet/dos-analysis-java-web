package fixture.repeated;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Source-only identity fixture; never starts an executor or runs a service. */
public final class RepeatedSubmit {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        1, 2, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.AbortPolicy());

    public static void caller(int size) {
        wrapper(new Resource(size));
    }

    public static void callerDepthTwo(int size) {
        outer(new Resource(size));
    }

    public static void callerMixedDepth(int size) {
        Resource resource = new Resource(size);
        wrapper(resource);
        outer(resource);
    }

    public static void callerSameDepthPrefixes(int size) {
        Resource resource = new Resource(size);
        outer(resource);
        otherOuter(resource);
    }

    private static void outer(Resource resource) {
        wrapper(resource);
    }

    private static void otherOuter(Resource resource) {
        wrapper(resource);
    }

    private static void wrapper(Resource resource) {
        Runnable same = () -> {
            try {
                if (resource.payload.length == 0) {
                    return;
                }
            } finally {
                resource.close();
            }
        };
        EXECUTOR.execute(same);
        EXECUTOR.execute(same);
    }

    private static final class Resource implements AutoCloseable {
        final byte[] payload;
        Resource(int size) { payload = new byte[size]; }
        public void close() { }
    }
}
