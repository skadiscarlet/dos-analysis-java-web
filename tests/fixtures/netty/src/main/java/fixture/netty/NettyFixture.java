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
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.util.CharsetUtil;

/** Positive: this initializer is installed by a supported bootstrap call. */
public class NettyFixture extends ChannelInitializer<Channel> {
    @Override
    protected void initChannel(Channel channel) {
        pipeline().addLast(new RegisteredHandler());
        pipeline().addLast(new FullRequestHandler());
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

class FullRequestHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
    private final TriggerService triggerService = new TriggerServiceImpl();

    @Override
    protected void channelRead0(ChannelHandlerContext context, FullHttpRequest request) {
        String uri = request.uri();
        String requestData = request.content().toString(CharsetUtil.UTF_8);
        new Runnable() {
            @Override
            public void run() {
                dispatch(uri, requestData);
            }
        }.run();
        consume(requestData);
    }

    private String dispatch(String uri, String requestData) {
        switch (uri) {
            case "/trigger":
                TriggerRequest trigger = JsonTool.fromJson(requestData, TriggerRequest.class);
                return triggerService.trigger(trigger);
            case "/beat":
                return "beat";
            default:
                return "unknown";
        }
    }

    private void consume(String requestData) {}
}

interface TriggerService {
    String trigger(TriggerRequest request);
}

class TriggerServiceImpl implements TriggerService {
    private final TriggerStore store = new TriggerStore();

    @Override
    public String trigger(TriggerRequest request) {
        return store.push(request);
    }
}

class TriggerStore {
    private final java.util.List<TriggerRequest> requests = new java.util.ArrayList<>();

    String push(TriggerRequest request) {
        requests.add(request);
        return "ok";
    }
}

class TriggerRequest {}

class JsonTool {
    static <T> T fromJson(String value, Class<T> type) { return null; }
}

class LookalikeRequestHandler extends SimpleChannelInboundHandler<FullHttpRequestLookalike> {
    @Override
    protected void channelRead0(ChannelHandlerContext context, FullHttpRequestLookalike request) {
        String requestData = request.content().toString(CharsetUtil.UTF_8);
        consume(requestData);
    }

    private void consume(String requestData) {}
}

class FullHttpRequestLookalike {
    ByteBufLookalike content() { return new ByteBufLookalike(); }
}

class ByteBufLookalike {
    String toString(java.nio.charset.Charset charset) { return ""; }
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
