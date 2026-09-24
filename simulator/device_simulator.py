"""
ColdChain AI - IoT telemetry simulator (beginner-friendly).

Publishes realistic JSON telemetry for EXISTING shipments over MQTT.

Flow:
  1. Fetch shipments + products from the FastAPI backend (so we know
     each product's allowed temperature range).
  2. For every tick, evolve each shipment's state with a random walk
     (temperature/humidity drift, occasional excursions, door events,
     battery drain, small GPS movement).
  3. Publish the JSON to:  <prefix>/shipments/<id>/telemetry

Usage (from the simulator/ folder, broker must be running):

    python device_simulator.py --count 30 --interval 1.0

Environment variables (no secrets hardcoded):
    MQTT_HOST, MQTT_PORT, MQTT_TOPIC_PREFIX, MQTT_USERNAME, MQTT_PASSWORD
"""

import argparse
import json
import os
import random
import time
import urllib.request
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Probability that a tick produces a temperature excursion.
EXCURSION_CHANCE = 0.10
# Probability that the container door is open on a tick.
DOOR_CHANCE = 0.05


def fetch_json(url: str):
    """Tiny urllib helper (avoids extra dependencies)."""
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_shipments(api_base: str) -> list[dict]:
    """Return shipments enriched with their product temperature limits."""
    shipments = fetch_json(f"{api_base}/shipments")
    products = {p["id"]: p for p in fetch_json(f"{api_base}/products")}

    enriched = []
    for ship in shipments:
        product = products.get(ship.get("product_id"))
        if product is None:
            print(f"[sim] Skipping shipment {ship['id']}: unknown product")
            continue
        enriched.append({"shipment": ship, "product": product})
    if not enriched:
        raise SystemExit(
            "[sim] No shipments with known products found. "
            "Create one via POST /products and POST /shipments first."
        )
    return enriched


def make_initial_state(entry: dict) -> dict:
    """Starting sensor values for one shipment."""
    product = entry["product"]
    ship = entry["shipment"]
    mid = (product["minimum_temperature"] + product["maximum_temperature"]) / 2
    width = product["maximum_temperature"] - product["minimum_temperature"]
    return {
        "temperature": round(mid + random.uniform(-width / 4, width / 4), 2),
        "humidity": round(
            (product["minimum_humidity"] + product["maximum_humidity"]) / 2, 2
        ),
        "latitude": ship.get("latitude") or 28.61,
        "longitude": ship.get("longitude") or 77.20,
        "battery_level": round(random.uniform(70, 100), 1),
    }


def next_reading(entry: dict, state: dict) -> dict:
    """
    Evolve the state by one tick and return the telemetry payload.
    Temperature/humidity use a random walk so values keep changing.
    """
    product = entry["product"]
    t_min, t_max = product["minimum_temperature"], product["maximum_temperature"]

    door_open = random.random() < DOOR_CHANCE
    if door_open:
        # An open door pushes the temperature towards/past the upper bound.
        state["temperature"] += random.uniform(0.3, 1.5)
    elif random.random() < EXCURSION_CHANCE:
        # Occasionally spike outside the allowed range.
        state["temperature"] += random.choice([-1, 1]) * random.uniform(1.0, 3.0)
    else:
        # Normal operation: drift back towards the middle of the range.
        mid = (t_min + t_max) / 2
        state["temperature"] += (mid - state["temperature"]) * 0.15
        state["temperature"] += random.gauss(0, 0.25)

    # Keep the value within a plausible sensor range.
    state["temperature"] = max(t_min - 5, min(t_max + 5, state["temperature"]))

    state["humidity"] += random.gauss(0, 1.5)
    state["humidity"] = max(0, min(100, state["humidity"]))

    # Slow GPS drift (the vehicle is moving).
    state["latitude"] += random.uniform(-0.002, 0.002)
    state["longitude"] += random.uniform(-0.002, 0.002)

    # Battery slowly drains.
    state["battery_level"] = max(0.0, round(state["battery_level"] - 0.05, 2))

    return {
        "shipment_id": entry["shipment"]["id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": round(state["temperature"], 2),
        "humidity": round(state["humidity"], 2),
        "latitude": round(state["latitude"], 6),
        "longitude": round(state["longitude"], 6),
        "battery_level": state["battery_level"],
        "door_open": door_open,
    }


def build_client(host: str, port: int, username: str, password: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="coldchain-simulator",
        protocol=mqtt.MQTTv311,
    )
    if username:
        client.username_pw_set(username, password)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client


def main() -> None:
    parser = argparse.ArgumentParser(description="ColdChain AI telemetry simulator")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument(
        "--prefix", default=os.getenv("MQTT_TOPIC_PREFIX", "coldchain")
    )
    parser.add_argument("--count", type=int, default=20, help="messages per shipment")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between ticks")
    args = parser.parse_args()

    username = os.getenv("MQTT_USERNAME", "")
    password = os.getenv("MQTT_PASSWORD", "")

    entries = load_shipments(args.api_base)
    states = {e["shipment"]["id"]: make_initial_state(e) for e in entries}
    print(f"[sim] Loaded {len(entries)} shipment(s); publishing to {args.host}:{args.port}")

    try:
        client = build_client(args.host, args.port, username, password)
    except OSError as exc:
        raise SystemExit(f"[sim] Cannot reach MQTT broker {args.host}:{args.port}: {exc}")

    try:
        for tick in range(args.count):
            for entry in entries:
                sid = entry["shipment"]["id"]
                payload = next_reading(entry, states[sid])
                topic = f"{args.prefix}/shipments/{sid}/telemetry"
                info = client.publish(topic, json.dumps(payload), qos=1)
                info.wait_for_publish(timeout=5)
                print(
                    f"[sim] tick={tick:02d} {topic} "
                    f"T={payload['temperature']:.2f}C RH={payload['humidity']:.1f}% "
                    f"door={'open' if payload['door_open'] else 'closed'} "
                    f"battery={payload['battery_level']:.1f}%"
                )
            time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()
        print("[sim] Done.")


if __name__ == "__main__":
    main()