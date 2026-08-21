package fixture.netty;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import javax.annotation.security.PermitAll;

import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.Channel;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelPipeline;

/** Positive: this initializer is installed by a supported bootstrap call. */
public class NettyFixture extends ChannelInitializer<Channel> {
    @Override
    protected void initChannel(Channel channel) {
        pipeline().addLast(new RegisteredHandler());
    }

    void unresolvedPipeline(ChannelInboundHandlerAdapter handler) {
        pipeline().addLast(handler);
    }

    static ServerBootstrap boot() {
        return new ServerBootstrap().childHandler(new NettyFixture());
    }
}

/** Negative: it defines a pipeline but is never passed to ServerBootstrap. */
class UninstalledInitializer extends ChannelInitializer<Channel> {
    @Override protected void initChannel(Channel channel) {
        pipeline().addLast(new UnregisteredHandler());
    }
}

class RegisteredHandler extends ChannelInboundHandlerAdapter {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final LinkedBlockingQueue<Object> unboundedQueue = new LinkedBlockingQueue<>();
    private final ArrayBlockingQueue<Object> finiteQueue = new ArrayBlockingQueue<>(8);

    @Override
    @PermitAll
    public void channelRead(ChannelHandlerContext context, Object message) {
        if (message == null) return;
        executor.submit(() -> consume(message));
        unboundedQueue.offer(message);
        if (!finiteQueue.offer(message)) return;
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
