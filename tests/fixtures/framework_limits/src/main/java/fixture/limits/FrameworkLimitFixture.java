package fixture.limits;

import com.fasterxml.jackson.core.StreamReadConstraints;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpObjectAggregator;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import javax.servlet.annotation.MultipartConfig;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

class JacksonBoundController {
    private static final int LIMIT = 1024;

    @PostMapping("/json")
    void json(int jacksonSize) {
        StreamReadConstraints.builder().maxStringLength(1024).build()
            .validateStringLength(jacksonSize);
        ByteBuffer.allocate(jacksonSize);
    }

    @PostMapping("/unbound-json")
    void unboundJson(int unboundJacksonSize) {
        StreamReadConstraints.builder().maxStringLength(1024).build();
        ByteBuffer.allocate(unboundJacksonSize);
    }

    @PostMapping("/plain-allocation")
    void plainAllocation(int requestedSize) {
        ByteBuffer.allocate(requestedSize);
    }

    @PostMapping("/clamped-allocation")
    void clampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, 1024));
    }

    @PostMapping("/hex-clamped-allocation")
    void hexClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, 0x400));
    }

    @PostMapping("/binary-clamped-allocation")
    void binaryClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, 0b10000000000));
    }

    @PostMapping("/expression-clamped-allocation")
    void expressionClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, 512 + 512));
    }

    @PostMapping("/constant-variable-clamped-allocation")
    void constantVariableClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, LIMIT));
    }

    @PostMapping("/server-derived-clamped-allocation")
    void serverDerivedClampedAllocation() {
        ByteBuffer.allocate(Math.min(serverDerivedValue(), 1024));
    }

    private int serverDerivedValue() {
        return 64;
    }

    @PostMapping("/zero-clamped-allocation")
    void zeroClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, 0));
    }

    @PostMapping("/negative-clamped-allocation")
    void negativeClampedAllocation(@RequestParam int requestedSize) {
        ByteBuffer.allocate(Math.min(requestedSize, -1));
    }

    @PostMapping("/constant-clamped-allocation")
    void constantClampedAllocation() {
        ByteBuffer.allocate(Math.min(-1, 1024));
    }
}

class Pipeline {
    Pipeline addLast(Object handler) { return this; }
}

class NettyInstaller {
    void install(Pipeline pipeline) {
        pipeline.addLast(new HttpObjectAggregator(1024));
        pipeline.addLast(new NettyBoundHandler());
        pipeline.addLast(new LooseNettyHandler());
    }
}

class NettyBoundHandler extends ChannelInboundHandlerAdapter {
    public void channelRead0(ChannelHandlerContext context, FullHttpRequest message) {
        ByteBuffer.allocate(message.content().readableBytes());
    }
}

class LooseNettyHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext context, Object looseMessage) {
        ByteBuffer.allocate((Integer) looseMessage);
    }
}

@MultipartConfig(maxRequestSize = 1024)
class UnrelatedMultipartServlet extends HttpServlet {
    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        ByteBuffer.allocate(1024); // unrelated multipart allocation
    }
}

@MultipartConfig(maxRequestSize = 1024)
class MultipartServlet extends HttpServlet {
    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        ByteBuffer.allocate(request.size());
    }
}

class SolrFormServlet extends HttpServlet {
    private static final int formdataUploadLimitInKB = 1024;

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        parseFormData(request.size());
    }

    private byte[] parseFormData(int length) {
        String contentType = "application/x-www-form-urlencoded";
        if (length > formdataUploadLimitInKB * 1024) {
            throw new IllegalArgumentException(contentType);
        }
        ByteArrayOutputStream keyStream = new ByteArrayOutputStream();
        return keyStream.toByteArray();
    }
}
