package io.netty.channel;

public abstract class SimpleChannelInboundHandler<T> extends ChannelInboundHandlerAdapter {
    protected abstract void channelRead0(ChannelHandlerContext context, T message);
}
