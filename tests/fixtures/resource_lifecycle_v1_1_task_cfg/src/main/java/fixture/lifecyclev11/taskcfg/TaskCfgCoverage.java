package fixture.lifecyclev11.taskcfg;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Focused source fixture for task CFG projection and executor-contract gaps. */
public final class TaskCfgCoverage {
    private static final int FIXED_CORE_WORKERS = 2;
    private static final int FIXED_MAX_WORKERS = 2;
    private static final int FIXED_QUEUE_CAPACITY = 2;
    private static int unresolvedQueueCapacity = 2;

    private static final ThreadPoolExecutor STABLE = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private static final ThreadPoolExecutor MUTABLE = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private static final ThreadPoolExecutor CONSTANTS = new ThreadPoolExecutor(
        FIXED_CORE_WORKERS,
        FIXED_MAX_WORKERS,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(FIXED_QUEUE_CAPACITY),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private static final ThreadPoolExecutor UNRESOLVED = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(unresolvedQueueCapacity),
        new ThreadPoolExecutor.AbortPolicy()
    );

    static {
        // A final reference does not freeze either worker bounds or the rejection handler.
        MUTABLE.setMaximumPoolSize(2);
        MUTABLE.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
    }

    private TaskCfgCoverage() {
    }

    public static void callerFinally(int requestedSize) {
        dispatchFinally(new TrackedResource(requestedSize));
    }

    private static void dispatchFinally(TrackedResource resource) {
        STABLE.execute(() -> {
            try {
                if (resource.isEmpty()) {
                    return;
                }
                throw new IllegalStateException("task failure");
            } finally {
                resource.close();
            }
        });
    }

    public static void callerExpressionBody(int requestedSize) {
        dispatchExpressionBody(new TrackedResource(requestedSize));
    }

    private static void dispatchExpressionBody(TrackedResource resource) {
        STABLE.execute(() -> resource.touch());
    }

    public static void callerMutableExecutor(int requestedSize) {
        dispatchMutableExecutor(new TrackedResource(requestedSize));
    }

    private static void dispatchMutableExecutor(TrackedResource resource) {
        MUTABLE.execute(() -> {
            resource.touch();
            return;
        });
    }

    public static void callerConstants(int requestedSize) {
        dispatchConstants(new TrackedResource(requestedSize));
    }

    private static void dispatchConstants(TrackedResource resource) {
        CONSTANTS.execute(() -> {
            try {
                resource.touch();
            } finally {
                resource.close();
            }
        });
    }

    public static void callerUnresolvedExecutor(int requestedSize) {
        dispatchUnresolvedExecutor(new TrackedResource(requestedSize));
    }

    private static void dispatchUnresolvedExecutor(TrackedResource resource) {
        UNRESOLVED.execute(() -> {
            resource.touch();
            return;
        });
    }

    public static void callerDirectClose(int requestedSize) {
        dispatchDirectClose(new TrackedResource(requestedSize));
    }

    private static void dispatchDirectClose(TrackedResource resource) {
        STABLE.execute(() -> {
            resource.close();
        });
    }

    public static void callerComplexFinally(int requestedSize) {
        dispatchComplexFinally(new TrackedResource(requestedSize));
    }

    private static void dispatchComplexFinally(TrackedResource resource) {
        STABLE.execute(() -> {
            try {
                resource.touch();
            } finally {
                resource.touch();
                resource.close();
            }
        });
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int requestedSize) {
            payload = new byte[Math.max(1, requestedSize)];
        }

        private boolean isEmpty() {
            return payload.length == 0;
        }

        private void touch() {
            payload[0] = 1;
        }

        @Override
        public void close() throws IllegalStateException {
            // Keep a modeled unchecked exception edge without taking it at runtime.
            if (payload.length < 0) {
                throw new IllegalStateException("unreachable fixture close failure");
            }
        }
    }
}
