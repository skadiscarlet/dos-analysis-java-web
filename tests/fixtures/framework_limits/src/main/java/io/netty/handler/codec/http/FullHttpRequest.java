package io.netty.handler.codec.http;

public class FullHttpRequest {
    public Content content() { return new Content(); }

    public static final class Content {
        public int readableBytes() { return 0; }
    }
}
