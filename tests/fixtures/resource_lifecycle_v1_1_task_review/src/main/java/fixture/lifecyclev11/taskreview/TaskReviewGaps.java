package fixture.lifecyclev11.taskreview;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Source-only regression cases for independent task relation coverage gaps. */
public final class TaskReviewGaps {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1), new ThreadPoolExecutor.AbortPolicy()
    );
    private static final ThreadPoolExecutor ALIASED_EXECUTOR = new ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1), new ThreadPoolExecutor.AbortPolicy()
    );
    private static final ThreadPoolExecutor EXECUTOR_ALIAS = ALIASED_EXECUTOR;
    private static TrackedResource shared;
    private static final List<TrackedResource> RESOURCES = new ArrayList<>();

    static {
        mutateAlias();
    }

    private static void mutateAlias() {
        EXECUTOR_ALIAS.setMaximumPoolSize(10);
    }

    public static void callerReassigned(int size) {
        reassigningWrapper(new TrackedResource(size));
    }

    private static void reassigningWrapper(TrackedResource resource) {
        resource = new TrackedResource(1);
        dispatchClosed(resource);
    }

    public static void callerPreserved(int size) {
        preservingWrapper(new TrackedResource(size));
    }

    private static void preservingWrapper(TrackedResource resource) {
        TrackedResource alias = resource;
        dispatchClosed(alias);
    }

    private static void dispatchClosed(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            try {
                if (resource.payload.length == 0) {
                    return;
                }
            } finally {
                resource.close();
            }
        });
    }

    public static void callerCloseFieldEscape(int size) {
        dispatchCloseFieldEscape(new TrackedResource(size));
    }

    private static void dispatchCloseFieldEscape(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            try {
                shared = resource;
            } finally {
                resource.close();
            }
        });
    }

    public static void callerCloseContainerEscape(int size) {
        dispatchCloseContainerEscape(new TrackedResource(size));
    }

    private static void dispatchCloseContainerEscape(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            try {
                RESOURCES.add(resource);
            } finally {
                resource.close();
            }
        });
    }

    public static void callerCloseUnknownCall(int size) {
        dispatchCloseUnknownCall(new TrackedResource(size));
    }

    private static void dispatchCloseUnknownCall(TrackedResource resource) {
        EXECUTOR.execute(() -> {
            try {
                observe(resource);
            } finally {
                resource.close();
            }
        });
    }

    private static void observe(TrackedResource resource) {
        shared = resource;
    }

    public static void callerStoredMethodReference(int size) {
        dispatchStoredMethodReference(new TrackedResource(size));
    }

    private static void dispatchStoredMethodReference(TrackedResource resource) {
        Runnable task = resource::touch;
        EXECUTOR.execute(task);
    }

    public static void callerStoredAnonymous(int size) {
        dispatchStoredAnonymous(new TrackedResource(size));
    }

    private static void dispatchStoredAnonymous(TrackedResource resource) {
        Runnable task = new Runnable() {
            @Override
            public void run() {
                resource.touch();
            }
        };
        EXECUTOR.execute(task);
    }

    public static void callerLocalLambda(int size) {
        TrackedResource resource = new TrackedResource(size);
        EXECUTOR.execute(() -> resource.touch());
    }

    public static void callerLocalMethodReference(int size) {
        TrackedResource resource = new TrackedResource(size);
        Runnable task = resource::touch;
        EXECUTOR.execute(task);
    }

    public static void callerLocalAnonymous(int size) {
        TrackedResource resource = new TrackedResource(size);
        Runnable task = new Runnable() {
            @Override
            public void run() {
                resource.touch();
            }
        };
        EXECUTOR.execute(task);
    }

    public static void callerFieldAliasExecutor(int size) {
        dispatchFieldAliasExecutor(new TrackedResource(size));
    }

    private static void dispatchFieldAliasExecutor(TrackedResource resource) {
        ALIASED_EXECUTOR.execute(() -> {
            try {
                resource.touch();
            } finally {
                resource.close();
            }
        });
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int size) {
            payload = new byte[Math.max(1, size)];
        }

        private void touch() {
            payload[0] = 1;
        }

        @Override
        public void close() throws IllegalStateException {
            if (payload.length < 0) {
                throw new IllegalStateException("unreachable fixture close failure");
            }
        }
    }
}
