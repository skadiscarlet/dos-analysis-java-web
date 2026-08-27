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

class JacksonBoundController {
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
