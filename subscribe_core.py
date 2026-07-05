#!/usr/bin/env python
import json

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TOPIC = "smart-campus/events/sensor"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT broker at {BROKER}:{PORT}")
        client.subscribe(TOPIC, qos=1)
        print(f"Subscribed to topic: {TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    try:
        event = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print("Received invalid JSON payload")
        return

    print("\nReceived sensor event:")
    print(json.dumps(event, indent=2, ensure_ascii=False))
    print(f"status={event.get('status')} alert_level={event.get('alert_level')} reason={event.get('reason')}")


def main() -> None:
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
