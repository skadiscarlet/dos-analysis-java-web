package org.eclipse.paho.client.mqttv3; public interface IMqttMessageListener { void messageArrived(String topic,MqttMessage message); }
