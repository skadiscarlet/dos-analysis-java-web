package io.netty.channel;
public abstract class ChannelInitializer<T> { protected abstract void initChannel(T channel); protected ChannelPipeline pipeline() { return new ChannelPipeline(); } }
