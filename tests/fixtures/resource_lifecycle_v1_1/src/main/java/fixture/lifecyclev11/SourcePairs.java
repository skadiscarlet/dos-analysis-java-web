package fixture.lifecyclev11;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class SourcePairs {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        2,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private SourcePairs() {
    }

    public static final void caller(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        wrapper1(resource);
    }

    private static final void wrapper1(TrackedResource resource) {
        wrapper2(resource);
    }

    private static final void wrapper2(TrackedResource resource) {
        Runnable task = () -> {
            try {
                if (resource.size() == 0) {
                    throw new IllegalStateException("empty resource");
                }
                resource.touch();
            } finally {
                resource.close();
            }
            return;
        };
        EXECUTOR.execute(task);
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        private int size() {
            return payload.length;
        }

        private void touch() {
            payload[0] = 1;
        }

        @Override
        public void close() {
            // The close is a source-level task effect, not an executor contract effect.
        }
    }
}
