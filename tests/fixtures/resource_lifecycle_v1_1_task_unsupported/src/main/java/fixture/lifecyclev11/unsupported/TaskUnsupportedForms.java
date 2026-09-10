package fixture.lifecyclev11.unsupported;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class TaskUnsupportedForms {
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy()
    );

    private TaskUnsupportedForms() {
    }

    public static final void callerSubmitCallable(int requestedSize) {
        submitCallable(new TrackedResource(requestedSize));
    }

    private static final void submitCallable(TrackedResource resource) {
        Future<Integer> future = EXECUTOR.submit(() -> {
            resource.touch();
            return 1;
        });
        future.cancel(true);
    }

    public static final void callerAnonymousRunnable(int requestedSize) {
        submitAnonymousRunnable(new TrackedResource(requestedSize));
    }

    private static final void submitAnonymousRunnable(TrackedResource resource) {
        EXECUTOR.execute(new Runnable() {
            @Override
            public void run() {
                resource.touch();
            }
        });
    }

    public static final void callerMethodReference(int requestedSize) {
        submitMethodReference(new TrackedResource(requestedSize));
    }

    private static final void submitMethodReference(TrackedResource resource) {
        EXECUTOR.execute(resource::touch);
    }

    public static final void callerLocalExecutor(int requestedSize) {
        submitLocalExecutor(new TrackedResource(requestedSize));
    }

    private static final void submitLocalExecutor(TrackedResource resource) {
        ThreadPoolExecutor executorAlias = EXECUTOR;
        executorAlias.execute(() -> resource.touch());
    }

    public static final void callerLocalCapture(int requestedSize) {
        submitLocalCapture(new TrackedResource(requestedSize));
    }

    private static final void submitLocalCapture(TrackedResource resource) {
        TrackedResource localCapture = resource;
        EXECUTOR.execute(() -> localCapture.touch());
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
            // Unsupported task forms must not infer callback release.
        }
    }
}
