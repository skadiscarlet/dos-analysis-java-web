package fixture.rc1;

import java.util.ArrayList;
import java.util.List;

public final class LoopResources {
    public static final class Resource implements AutoCloseable {
        public void close() { }
    }

    public void retiredEachIteration(int count) {
        while (count-- > 0) {
            Resource resource = new Resource();
            resource.close();
            resource = null;
        }
    }

    public void retainedEachIteration(int count) {
        List<Resource> retained = new ArrayList<>();
        while (count-- > 0) {
            Resource resource = new Resource();
            retained.add(resource);
        }
    }

    public void mutuallyExclusiveCloseThenLoop(boolean chooseFirst, int count) {
        Resource first = new Resource();
        Resource second = new Resource();
        if (chooseFirst) {
            first.close();
        } else {
            second.close();
        }
        while (count-- > 0) { }
    }
}
