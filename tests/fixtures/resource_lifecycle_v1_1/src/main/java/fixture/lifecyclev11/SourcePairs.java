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

    /* Task 6 source-pair fixtures.  Keep the original caller above stable: it
     * remains the focused extraction regression used by Tasks 2--5. */
    private static final ThreadPoolExecutor SUPPORTED_EXECUTOR = new ThreadPoolExecutor(
        2,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(3),
        new ThreadPoolExecutor.AbortPolicy()
    );
    private static int unknownQueueCapacity = 3;
    private static final ThreadPoolExecutor UNKNOWN_CAPACITY_EXECUTOR = new ThreadPoolExecutor(
        2,
        2,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(unknownQueueCapacity),
        new ThreadPoolExecutor.AbortPolicy()
    );
    private static TrackedResource s2Shared;
    private static boolean taskFailure;

    public static final void s1Sync(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            resource.close();
        }
    }

    public static final void s1TaskWrapped(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        s1TaskWrapper(resource);
    }

    private static final void s1TaskWrapper(TrackedResource resource) {
        dispatchExact(resource);
    }

    public static final void s2TaskOnly(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        dispatchExact(resource);
    }

    public static final void s2FieldHolder(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        s2Shared = resource;
        dispatchExact(resource);
    }

    public static final void s3AllExitsClose(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            resource.close();
        }
    }

    public static final void s3MissingExceptionalClose(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        resource.close();
    }

    public static final void s4Direct(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            resource.close();
        }
    }

    public static final void s4DepthTwo(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
            s4Wrapper1(resource);
        } finally {
            resource.close();
        }
    }

    private static final void s4Wrapper1(TrackedResource resource) {
        s4Wrapper2(resource);
    }

    private static final void s4Wrapper2(TrackedResource resource) {
        // Exact depth-2 identity propagation; no resource effect occurs here.
        return;
    }

    public static final void s5VerifiedCapacity(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        dispatchExact(resource);
    }

    public static final void s5UnknownCapacity(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        dispatchUnknownCapacity(resource);
    }

    public static final void s6SupportedExecutor(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        dispatchExact(resource);
    }

    public static final void s6UnresolvedExecutor(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        dispatchUnresolvedExecutor(resource);
    }

    private static final void dispatchExact(TrackedResource resource) {
        SUPPORTED_EXECUTOR.execute(() -> {
            try {
                if (taskFailure) {
                    throw new IllegalStateException("fixture task failure");
                }
                return;
            } finally {
                resource.close();
            }
        });
    }

    private static final void dispatchUnknownCapacity(TrackedResource resource) {
        UNKNOWN_CAPACITY_EXECUTOR.execute(() -> {
            try {
                if (taskFailure) {
                    throw new IllegalStateException("fixture task failure");
                }
                return;
            } finally {
                resource.close();
            }
        });
    }

    private static final void dispatchUnresolvedExecutor(TrackedResource resource) {
        ThreadPoolExecutor executorAlias = SUPPORTED_EXECUTOR;
        executorAlias.execute(() -> {
            try {
                if (taskFailure) {
                    throw new IllegalStateException("fixture task failure");
                }
                return;
            } finally {
                resource.close();
            }
        });
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
