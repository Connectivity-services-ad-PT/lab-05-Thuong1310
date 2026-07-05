#!/usr/bin/env python
import argparse
import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "smart-campus/events/sensor"


def build_payload(event_id: str, status: str, alert_level: str) -> dict:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "event_type": "sensor.reading.processed",
        "source_service": "team-iot",
        "raw_event_id": event_id,
        "device_id": "esp32-lab-a101",
        "location": "Lab A101",
        "temperature_c": 42.1,
        "humidity_percent": 71.2,
        "motion_detected": True,
        "co2_ppm": 710,
        "smoke_ppm": 0.03,
        "battery_percent": 86,
        "status": status,
        "alert_level": alert_level,
        "reason": "temperature_too_high",
        "timestamp": now,
    }


def publish_event(broker: str, port: int, topic: str, payload: dict) -> None:
    client = mqtt.Client()
    client.connect(broker, port)
    client.publish(topic, json.dumps(payload), qos=1)
    client.disconnect()
    print(f"Published event to mqtt://{broker}:{port}/{topic}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a sample IoT sensor event to MQTT.")
    parser.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="MQTT topic to publish")
    parser.add_argument("--event-id", default="raw-iot-abc123", help="Raw event id")
    parser.add_argument("--status", default="danger", choices=["normal", "warning", "danger", "sensor_error", "invalid_device"], help="Event status")
    parser.add_argument("--alert-level", default="high", choices=["low", "medium", "high"], help="Alert level")
    args = parser.parse_args()

    payload = build_payload(args.event_id, args.status, args.alert_level)
    publish_event(args.broker, args.port, args.topic, payload)
