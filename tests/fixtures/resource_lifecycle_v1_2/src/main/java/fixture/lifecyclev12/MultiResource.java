package fixture.lifecyclev12;

/** Synthetic multi-resource acceptance fixture, not an independent project. */
public final class MultiResource {
    public static final class Resource implements AutoCloseable {
        public void close() {}
    }

    public void twoResources() {
        Resource first = new Resource(); Resource second = new Resource();
        try {
            first.close();
        } finally {
            second.close();
        }
    }
}
