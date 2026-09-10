package fixture.lifecyclev11.policies;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class TaskExecutorPolicies {
    private static final ThreadPoolExecutor CALLER_RUNS = new ThreadPoolExecutor(
        1,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.CallerRunsPolicy()
    );

    private static final ThreadPoolExecutor DISCARD = new ThreadPoolExecutor(
        1,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.DiscardPolicy()
    );

    private static final ThreadPoolExecutor DISCARD_OLDEST = new ThreadPoolExecutor(
        1,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.DiscardOldestPolicy()
    );

    private static final ThreadPoolExecutor ESCAPED = new ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1), new ThreadPoolExecutor.AbortPolicy()
    );

    public static ThreadPoolExecutor exposedExecutor() {
        ThreadPoolExecutor firstAlias = ESCAPED;
        ThreadPoolExecutor secondAlias = firstAlias;
        return secondAlias;
    }

    public static void callerEscapedExecutor(int requestedSize) {
        dispatchEscapedExecutor(new TrackedResource(requestedSize));
    }

    private static void dispatchEscapedExecutor(TrackedResource resource) {
        ESCAPED.execute(() -> {
            resource.touch();
            return;
        });
    }

    private TaskExecutorPolicies() {
    }

    public static final void callerCallerRuns(int requestedSize) {
        dispatchCallerRuns(new TrackedResource(requestedSize));
    }

    private static final void dispatchCallerRuns(TrackedResource resource) {
        CALLER_RUNS.execute(() -> {
            resource.touch();
            return;
        });
    }

    public static final void callerDiscard(int requestedSize) {
        dispatchDiscard(new TrackedResource(requestedSize));
    }

    private static final void dispatchDiscard(TrackedResource resource) {
        DISCARD.execute(() -> {
            resource.touch();
            return;
        });
    }

    public static final void callerDiscardOldest(int requestedSize) {
        dispatchDiscardOldest(new TrackedResource(requestedSize));
    }

    private static final void dispatchDiscardOldest(TrackedResource resource) {
        DISCARD_OLDEST.execute(() -> {
            resource.touch();
            return;
        });
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int requestedSize) {
            payload = new byte[Math.max(1, requestedSize)];
        }

        private void touch() {
            payload[0] = 1;
        }

        @Override
        public void close() {
            // Unsupported rejection policies do not imply callback release.
        }
    }
}
