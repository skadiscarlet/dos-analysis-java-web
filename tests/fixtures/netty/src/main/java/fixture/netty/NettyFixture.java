package fixture.netty;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;

class Channel {}
class ChannelHandlerContext {}
class ChannelPipeline {
    void addLast(ChannelInboundHandlerAdapter handler) {}
}
abstract class ChannelInitializer<T> {
    protected abstract void initChannel(T channel);
    ChannelPipeline pipeline() { return new ChannelPipeline(); }
}
class ChannelInboundHandlerAdapter {
    public void channelRead(ChannelHandlerContext context, Object message) {}
}

public class NettyFixture extends ChannelInitializer<Channel> {
    @Override
    protected void initChannel(Channel channel) {
        pipeline().addLast(new RegisteredHandler());
    }

    void unresolvedPipeline(ChannelInboundHandlerAdapter handler) {
        pipeline().addLast(handler);
    }
}

class RegisteredHandler extends ChannelInboundHandlerAdapter {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final LinkedBlockingQueue<Object> unboundedQueue = new LinkedBlockingQueue<>();
    private final ArrayBlockingQueue<Object> finiteQueue = new ArrayBlockingQueue<>(8);

    @Override
    public void channelRead(ChannelHandlerContext context, Object message) {
        if (message == null) return;
        executor.submit(() -> consume(message));
        unboundedQueue.offer(message);
        finiteQueue.offer(message);
        try {
            consume(message);
        } finally {
            finiteQueue.remove(message);
        }
    }

    private void consume(Object message) {}
}

class UnregisteredHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext context, Object message) {}
}

class FakePipeline {
    void addLast(Object handler) {}
}
class FakeNettyLookalike {
    void channelRead(Object context, Object message) {}
    void initChannel(FakePipeline pipeline) { pipeline.addLast(new FakeNettyLookalike()); }
}

class DynamicPipelineRegistration extends ChannelInitializer<Channel> {
    @Override
    protected void initChannel(Channel channel) {}

    void register(String handlerName) throws Exception {
        Class.forName(handlerName);
    }
}
