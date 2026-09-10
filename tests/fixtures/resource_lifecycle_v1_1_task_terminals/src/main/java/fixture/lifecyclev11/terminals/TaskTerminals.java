package fixture.lifecyclev11.terminals;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class TaskTerminals {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private TaskTerminals() {
    }

    public static final void callerCaughtThrow(int requestedSize) {
        dispatchCaughtThrow(new TrackedResource(requestedSize));
    }

    private static final void dispatchCaughtThrow(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            try {
                throw new IllegalStateException("caught");
            } catch (IllegalStateException ignored) {
                resource.touch();
            }
            return;
        });
    }

    public static final void callerImplicitNormal(int requestedSize) {
        dispatchImplicitNormal(new TrackedResource(requestedSize));
    }

    private static final void dispatchImplicitNormal(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            resource.touch();
        });
    }

    public static final void callerCallException(int requestedSize) {
        dispatchCallException(new TrackedResource(requestedSize));
    }

    private static final void dispatchCallException(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            resource.close();
            return;
        });
    }

    public static void callerMultipleNormalExits(int requestedSize) {
        dispatchMultipleNormalExits(new TrackedResource(requestedSize));
    }

    private static void dispatchMultipleNormalExits(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            if (resource.payload.length == 0) {
                return;
            }
            return;
        });
    }

    public static void callerMultipleExceptionalExits(int requestedSize) {
        dispatchMultipleExceptionalExits(new TrackedResource(requestedSize));
    }

    private static void dispatchMultipleExceptionalExits(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            if (resource.payload.length == 0) {
                throw new IllegalArgumentException("first exit");
            }
            throw new IllegalStateException("second exit");
        });
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        private void touch() {
            payload[0] = 1;
        }

        @Override
        public void close() {
            // The call site can still terminate exceptionally at runtime.
        }
    }
}
