package fixture.mqtt;

class MqttMessage {
    byte[] getPayload() { return new byte[0]; }
}
interface IMqttMessageListener {
    void messageArrived(String topic, MqttMessage message);
}
class MqttAsyncClient {
    void subscribe(String topic, int qos, IMqttMessageListener listener) {}
}

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
