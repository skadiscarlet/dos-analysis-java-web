package io.netty.bootstrap;
import io.netty.channel.Channel;
import io.netty.channel.ChannelInitializer;
public class ServerBootstrap { public ServerBootstrap childHandler(ChannelInitializer<Channel> initializer) { return this; } public ServerBootstrap handler(ChannelInitializer<Channel> initializer) { return this; } }
