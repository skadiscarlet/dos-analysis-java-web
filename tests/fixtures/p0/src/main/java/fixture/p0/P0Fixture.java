package fixture.p0;

import java.nio.ByteBuffer;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.annotation.security.PermitAll;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class P0Fixture {
    private static final Map<String, byte[]> GLOBAL = new ConcurrentHashMap<>();
    private final ArrayBlockingQueue<byte[]> finite = new ArrayBlockingQueue<>(8);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @PermitAll
    @RequestMapping("/materialize")
    public void materialize(@RequestBody byte[] body) {
        body.clone();
    }

    @PermitAll
    @RequestMapping("/allocate")
    public void allocate(@RequestParam("size") int size) {
        ByteBuffer.allocate(size);
    }

    @PermitAll
    @RequestMapping("/map")
    public void distinctKey(@RequestParam("key") String key) {
        GLOBAL.put(key, new byte[1]);
    }

    @PermitAll
    @RequestMapping("/executor")
    public void executorQueue(@RequestBody byte[] body) {
        executor.submit(() -> consume(body));
    }

    @PermitAll
    @RequestMapping("/finite")
    public void finiteQueue(@RequestBody byte[] body) {
        if (!finite.offer(body)) return;
    }

    @PermitAll
    @RequestMapping("/post-guard")
    public void postMaterializationGuard(@RequestBody byte[] body) {
        body.clone();
        if (body.length > 8) return;
        ByteBuffer.allocate(body.length);
    }

    @PermitAll
    @RequestMapping("/wrapper-guard")
    public void wrapperGuard(@RequestParam("size") int size) {
        throwIfOversize(size);
        ByteBuffer.allocate(size);
    }

    @PermitAll
    @RequestMapping("/wrapper-after")
    public void wrapperAfterGrowth(@RequestParam("size") int size) {
        ByteBuffer.allocate(size);
        throwIfOversize(size);
    }

    @PermitAll
    @RequestMapping("/wrapper-caught")
    public void wrapperCaughtThrow(@RequestParam("size") int size) {
        caughtThrowIfOversize(size);
        ByteBuffer.allocate(size);
    }

    @PermitAll
    @RequestMapping("/wrapper-depth3")
    public void wrapperDepthThree(@RequestParam("size") int size) {
        guardLevelOne(size);
        ByteBuffer.allocate(size);
    }

    @PermitAll
    @RequestMapping("/wrapper-return")
    public void wrapperReturnIsNotAGuard(@RequestParam("size") int size) {
        returnIfOversize(size);
        ByteBuffer.allocate(size);
    }

    private void throwIfOversize(int size) {
        if (size > 8) throw new IllegalArgumentException();
    }

    private void returnIfOversize(int size) {
        if (size > 8) return;
    }

    private void caughtThrowIfOversize(int size) {
        if (size > 8) {
            try { throw new IllegalArgumentException(); }
            catch (IllegalArgumentException ignored) { }
        }
    }

    private void guardLevelOne(int size) { guardLevelTwo(size); }
    private void guardLevelTwo(int size) { throwIfOversize(size); }

    @PermitAll
    @RequestMapping("/success-release")
    public void successOnlyRelease(@RequestParam("key") String key) {
        GLOBAL.put(key, new byte[1]);
        GLOBAL.remove(key);
    }

    @PermitAll
    @RequestMapping("/async-consumer")
    public void asyncConsumer(@RequestBody byte[] body) {
        executor.submit(() -> consume(body));
    }

    private void consume(byte[] body) { }
}
