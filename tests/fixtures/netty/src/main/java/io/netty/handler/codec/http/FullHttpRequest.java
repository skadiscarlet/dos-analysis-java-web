package io.netty.handler.codec.http;

import io.netty.buffer.ByteBuf;

public class FullHttpRequest {
    public ByteBuf content() { return new ByteBuf(); }
    public String uri() { return "/"; }
}
