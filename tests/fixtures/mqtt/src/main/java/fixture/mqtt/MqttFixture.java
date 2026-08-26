package fixture.mqtt;
import org.eclipse.paho.client.mqttv3.*;
import javax.annotation.security.PermitAll;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class MqttFixture {
    void register(MqttAsyncClient client) {
        client.subscribe("items/topic", 1, new RegisteredListener());
    }

    void dynamicGap(MqttAsyncClient client, String topic, IMqttMessageListener listener) {
        client.subscribe(topic, 1, listener);
    }

    void unresolvedListener(MqttAsyncClient client, IMqttMessageListener listener) {
        client.subscribe("fixed/topic", 1, listener);
    }
}

class FakeClient {
    void subscribe(String topic, int qos, Object listener) {}
}
class FakeMqttLookalike {
    void register(FakeClient client) {
        client.subscribe("fake/topic", 1, new FakeMqttLookalike());
    }
    void messageArrived(String topic, MqttMessage message) {}
}

class RegisteredListener implements IMqttMessageListener {
    @Override
    @PermitAll
    public void messageArrived(String topic, MqttMessage message) {
        byte[] materialized = message.getPayload().clone();
        if (materialized.length > 4096) return;
        try {
            consume(materialized);
        } finally {
            materialized = null;
        }
    }

    private void consume(byte[] payload) {}
}

class UnregisteredListener implements IMqttMessageListener {
    @Override
    public void messageArrived(String topic, MqttMessage message) {}
}

class BrokerMqttMessage { int packetId() { return 1; } }
class BrokerContext {}
class BrokerChannel {}
class ChannelPipeline {
    ChannelPipeline addLast(String name, ChannelDuplexHandler handler) { return this; }
    ChannelPipeline addLast(ChannelDuplexHandler handler) { return this; }
}
abstract class ChannelInitializer<T> {
    protected abstract void initChannel(T channel);
    ChannelPipeline pipeline() { return new ChannelPipeline(); }
}
class ChannelDuplexHandler {
    public void channelRead(BrokerContext context, BrokerMqttMessage message) {}
}
class NettyMqttHandler extends ChannelDuplexHandler {
    @Override
    public void channelRead(BrokerContext context, BrokerMqttMessage message) {}
}
class MqttNettyUtils {
    static BrokerMqttMessage validateMessage(Object message) { return (BrokerMqttMessage) message; }
}
class MQTTConnection {
    void processProtocol(BrokerContext context, BrokerMqttMessage message) {
        Runnable task = () -> new PublishProcessor().processRequest(context, message);
        new BrokerExecutor().submit(task);
    }
    void processPublishMessage(BrokerMqttMessage message) { processQos2(message); }
    private void processQos2(BrokerMqttMessage message) {
        new MqttSession().receivedPublishQos2(message.packetId(), new DeviceMessage());
    }
}
class PublishProcessor {
    void processRequest(BrokerContext context, BrokerMqttMessage message) {
        new MQTTConnection().processPublishMessage(message);
    }
}
class BrokerExecutor { void submit(Runnable task) {} }
class DeviceMessage {}
class MqttSession {
    private final Map<Integer, DeviceMessage> qos2Receiving = new ConcurrentHashMap<>();
    void receivedPublishQos2(int originPacketId, DeviceMessage message) {
        qos2Receiving.put(originPacketId, message);
    }
}
class ConvertedNettyMqttHandler extends ChannelDuplexHandler {
    public void channelRead(BrokerContext context, Object message) {
        BrokerMqttMessage mqttMessage = MqttNettyUtils.validateMessage(message);
        new MQTTConnection().processProtocol(context, mqttMessage);
    }
}
class BrokerBootstrap {
    ChannelInitializer<BrokerChannel> registeredInitializer() {
        return new ChannelInitializer<BrokerChannel>() {
            @Override protected void initChannel(BrokerChannel channel) {
                pipeline().addLast("nettyMqttHandler", new NettyMqttHandler());
                pipeline().addLast("convertedNettyMqttHandler", new ConvertedNettyMqttHandler());
            }
        };
    }

    ChannelInitializer<BrokerChannel> dynamicInitializer(ChannelDuplexHandler handler) {
        return new ChannelInitializer<BrokerChannel>() {
            @Override protected void initChannel(BrokerChannel channel) {
                pipeline().addLast(handler);
            }
        };
    }
}
class UnregisteredBrokerHandler extends ChannelDuplexHandler {
    @Override public void channelRead(BrokerContext context, BrokerMqttMessage message) {}
}

class MqttDecoder {}
class Connection { Connection addHandler(Object handler) { return this; } }
class TcpServer {
    TcpServer doOnConnection(ConnectionConsumer consumer) { return this; }
}
interface ConnectionConsumer { void accept(Connection connection); }
class ProtocolAdaptor { void chooseProtocol(Object channel, BrokerMqttMessage message, Object context) {} }
class SmqttReceiveContext {
    private final ProtocolAdaptor adaptor = new ProtocolAdaptor();
    public void apply(Object channel) {}
    public void accept(Object channel, BrokerMqttMessage message) {
        adaptor.chooseProtocol(channel, message, this);
    }
}
class MqttReceiver {
    private void newTcpServer(TcpServer server, SmqttReceiveContext context) {
        server.doOnConnection(connection -> {
            connection.addHandler(new MqttDecoder());
            context.apply(connection);
        });
    }
}
class AmbiguousMqttReceiver {
    private void newTcpServer(TcpServer server, SmqttReceiveContext first, SmqttReceiveContext second) {
        server.doOnConnection(connection -> {
            connection.addHandler(new MqttDecoder());
            first.apply(connection);
            second.apply(connection);
        });
    }
}
