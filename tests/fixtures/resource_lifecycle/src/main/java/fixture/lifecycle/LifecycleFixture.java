package fixture.lifecycle;

import java.util.Map;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Executor;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiFunction;
import java.util.function.Function;

public final class LifecycleFixture {
    private final Queue<TrackedResource> unbounded = new ConcurrentLinkedQueue<>();
    private final BlockingQueue<TrackedResource> bounded = new ArrayBlockingQueue<>(2);
    private final ArrayBlockingQueue<TrackedResource> concreteBounded = new ArrayBlockingQueue<>(3);
    private final CustomBoundedQueue<TrackedResource> customBounded = new CustomBoundedQueue<>(4);
    private BlockingQueue<TrackedResource> mutableBounded = new ArrayBlockingQueue<>(2);
    private final Queue<byte[]> byteArrays = new ConcurrentLinkedQueue<>();
    private final Map<String, Object> objects = new ConcurrentHashMap<>();
    private final Executor taskExecutor = task -> { };
    private final PlainResource initializedPojo = new PlainResource(1);
    private static final PlainResource globalInitializedPojo = new PlainResource(2);
    private TrackedResource saved;
    private PlainResource savedPojo;
    private byte[] savedBytes;

    public void syncClosed(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            resource.close();
        }
    }

    public void preTryMayThrow(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        mayThrowBeforeTry(requestedSize);
        try {
            // The finally block is not entered when the preceding call throws.
        } finally {
            resource.close();
        }
    }

    private static void mayThrowBeforeTry(int requestedSize) {
        if (requestedSize < 0) {
            throw new IllegalArgumentException("negative size");
        }
    }

    public void conditionalFinally(int requestedSize, boolean closeIt) {
        TrackedResource resource = new TrackedResource(requestedSize);
        try {
            // The conditional close below must not be promoted to must-release.
        } finally {
            if (closeIt) {
                resource.close();
            }
        }
    }

    public void finallyPredecessorMayThrow(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            mayThrowBeforeTry(requestedSize);
            resource.close();
        }
    }

    public void overloadedCloseDoesNotRelease(int requestedSize) {
        TrackedResource resource = null;
        try {
            resource = new TrackedResource(requestedSize);
        } finally {
            resource.close(true);
        }
    }

    public void forUpdateRepeatedAllocation(int requestedSize) {
        TrackedResource resource = null;
        try {
            for (int index = 0; index < requestedSize; resource = new TrackedResource(index++)) {
                // The update may overwrite multiple live resources before finally closes the last one.
            }
        } finally {
            resource.close();
        }
    }

    public void whileConditionRepeatedAllocation(int requestedSize) {
        TrackedResource resource = null;
        try {
            while (requestedSize-- > 0 && (resource = new TrackedResource(requestedSize)) != null) {
                // The condition may overwrite multiple live resources before finally closes the last one.
            }
        } finally {
            resource.close();
        }
    }

    public void conditionalAlias(int requestedSize, boolean chooseResource) {
        TrackedResource resource = new TrackedResource(requestedSize);
        TrackedResource alias = chooseResource ? resource : null;
        alias.close();
    }

    public void overwrittenAlias(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        resource = new TrackedResource(requestedSize + 1);
        resource.close();
    }

    public void selectedAlias(int requestedSize, boolean chooseFirst) {
        TrackedResource first = new TrackedResource(requestedSize);
        TrackedResource second = new TrackedResource(requestedSize + 1);
        TrackedResource selected = chooseFirst ? first : second;
        selected.close();
    }

    public void receiverEscape(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        resource.touch();
    }

    TrackedResource returnEscape(int requestedSize) {
        return new TrackedResource(requestedSize);
    }

    public void asyncQueued(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        unbounded.add(resource);
    }

    public boolean boundedQueued(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        if (!bounded.offer(resource)) {
            resource.close();
            return false;
        }
        return true;
    }

    public boolean concreteBoundedQueued(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        if (!concreteBounded.offer(resource)) {
            resource.close();
            return false;
        }
        return true;
    }

    public boolean customSubtypeQueued(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        if (!customBounded.offer(resource)) {
            resource.close();
            return false;
        }
        return true;
    }

    public boolean mutableReassignedQueued(int requestedSize) {
        mutableBounded = new LinkedBlockingQueue<>();
        TrackedResource resource = new TrackedResource(requestedSize);
        if (!mutableBounded.offer(resource)) {
            resource.close();
            return false;
        }
        return true;
    }

    public void fieldRetained(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        saved = resource;
        resource.close();
    }

    public void pojoFieldRetained(int requestedSize) {
        PlainResource resource = new PlainResource(requestedSize);
        savedPojo = resource;
    }

    public void byteArrayFieldRetained(int requestedSize) {
        byte[] resource = new byte[Math.max(0, requestedSize)];
        savedBytes = resource;
    }

    public void byteArrayContainerRetained(int requestedSize) {
        byte[] resource = new byte[Math.max(0, requestedSize)];
        byteArrays.add(resource);
    }

    public void temporaryPojo(int requestedSize) {
        new PlainResource(requestedSize).touch();
    }

    public void explicitTaskCapture(int requestedSize) {
        taskExecutor.execute(new PlainTask(requestedSize));
    }

    public void mapCallbackIsNotStored() {
        objects.computeIfAbsent("key", new MappingFunction());
    }

    public void mapPutValueIsStored(int requestedSize) {
        objects.put("key", new PlainResource(requestedSize));
    }

    public void mapReplaceValueIsStored(int requestedSize) {
        objects.replace("key", new PlainResource(requestedSize));
    }

    public void mapCompareReplaceNewValueIsStored(int requestedSize) {
        objects.replace("key", "old", new PlainResource(requestedSize));
    }

    public void mapCompareReplaceOldValueIsNotStored(int requestedSize) {
        objects.replace("key", new PlainResource(requestedSize), "new");
    }

    public void mapMergeValueIsStored(int requestedSize) {
        objects.merge("key", new PlainResource(requestedSize), (oldValue, newValue) -> oldValue);
    }

    public void mapMergeCallbackIsNotStored() {
        objects.merge("key", "value", new MergeFunction());
    }

    public void twinEscapingAllocations(int requestedSize) {
        saved = new TrackedResource(requestedSize); unbounded.add(new TrackedResource(requestedSize + 1));
    }

    public void overloadedResource(int requestedSize) {
        saved = new TrackedResource(requestedSize);
    }

    public void overloadedResource(String requestedSize) {
        saved = new TrackedResource(requestedSize.length());
    }

    public void polymorphicEscape(int requestedSize, ResourceObserver observer) {
        TrackedResource resource = new TrackedResource(requestedSize);
        observer.inspect(resource);
    }

    interface ResourceObserver {
        void inspect(TrackedResource resource);
    }

    static final class FirstObserver implements ResourceObserver {
        @Override
        public void inspect(TrackedResource resource) {
            resource.touch();
        }
    }

    static final class SecondObserver implements ResourceObserver {
        @Override
        public void inspect(TrackedResource resource) {
            resource.close();
        }
    }

    static final class MappingFunction implements Function<String, Object> {
        @Override
        public Object apply(String key) {
            return key;
        }
    }

    static final class CustomBoundedQueue<E> extends ArrayBlockingQueue<E> {
        CustomBoundedQueue(int capacity) {
            super(capacity);
        }
    }

    static final class MergeFunction implements BiFunction<Object, Object, Object> {
        @Override
        public Object apply(Object oldValue, Object newValue) {
            return oldValue;
        }
    }

    static final class PlainTask implements Runnable {
        private final byte[] payload;

        PlainTask(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        @Override
        public void run() {
            if (payload.length > 0) {
                payload[0] = 1;
            }
        }
    }

    static final class PlainResource {
        private final byte[] payload;

        PlainResource(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        void touch() {
            if (payload.length > 0) {
                payload[0] = 1;
            }
        }
    }

    static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        TrackedResource(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        void touch() {
            if (payload.length > 0) {
                payload[0] = 1;
            }
        }

        @Override
        public void close() {
            // The fixture models the obligation; it does not allocate a workload.
        }

        void close(boolean ignored) {
            // This overload deliberately does not implement the AutoCloseable contract.
        }
    }
}
