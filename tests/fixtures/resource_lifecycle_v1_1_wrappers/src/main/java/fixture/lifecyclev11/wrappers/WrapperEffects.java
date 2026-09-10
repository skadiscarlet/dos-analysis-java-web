package fixture.lifecyclev11.wrappers;

public final class WrapperEffects {
    private static TrackedResource SHARED;
    private TrackedResource instanceRetained;

    public static final void callerEffects(int requestedSize, boolean closeIt) {
        TrackedResource resource = new TrackedResource(requestedSize);
        wrapperEffect1(resource, closeIt);
    }

    private static final void wrapperEffect1(
        TrackedResource resource,
        boolean closeIt
    ) {
        wrapperEffect2(resource, closeIt);
    }

    private static final void wrapperEffect2(
        TrackedResource resource,
        boolean closeIt
    ) {
        SHARED = resource;
        if (closeIt) {
            resource.close();
        }
        return;
    }

    public static final TrackedResource callerReturn(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        return wrapperReturn1(resource);
    }

    private static final TrackedResource wrapperReturn1(TrackedResource resource) {
        return wrapperReturn2(resource);
    }

    private static final TrackedResource wrapperReturn2(TrackedResource resource) {
        return resource;
    }

    public static final void callerInstanceField(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        new WrapperEffects().storeInstance(resource);
    }

    private final void storeInstance(TrackedResource resource) {
        instanceRetained = resource;
        return;
    }

    public static final void callerReassigned(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        overwriteParameter(resource);
    }

    private static final void overwriteParameter(TrackedResource resource) {
        resource = new TrackedResource(1);
        wrapperEffect2(resource, true);
    }

    public static final void callerReturnClosed(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        TrackedResource returned = wrapperReturn1(resource);
        returned.close();
    }

    public static final void callerRepeated(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        wrapperEffect1(resource, false); wrapperEffect1(resource, true);
    }

    public static final void callerFinallyWrapper(int requestedSize) {
        TrackedResource resource = new TrackedResource(requestedSize);
        try {
            throw new IllegalArgumentException("pending exception");
        } finally {
            wrapperEffect1(resource, true);
        }
    }

    private static final class TrackedResource implements AutoCloseable {
        private final byte[] payload;

        private TrackedResource(int requestedSize) {
            payload = new byte[Math.max(0, requestedSize)];
        }

        @Override
        public void close() {
            // Source-level effect only.
        }
    }
}
