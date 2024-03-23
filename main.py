import dht
import json
import machine
import network
import requests
import sys
import time

# Define the default wait time for next reading
DEFAULT_WAIT_TIME = 60


def load_config(config_file: str):
    config = {}
    try:
        with open(config_file) as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{config_file}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in config file '{config_file}'.")
    return config


def connect_to_wifi(ssid: str, key: str, timeout_sec: int = 30):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to network...")
        wlan.connect(ssid, key)
        start_time = time.time()
        while not wlan.isconnected():
            if time.time() - start_time > timeout_sec:
                print("Connection timed out.")
                return False
            time.sleep(1)  # Wait for 1 second before next attempt
    return True


def init_dht_sensor(pin: int) -> dht.DHT11:
    try:
        dht_sensor = dht.DHT11(machine.Pin(pin))
    except ValueError as ve:
        raise ValueError(f"Invalid pin number: {pin}") from ve
    except OSError as oe:
        raise OSError("Error initializing DHT11 sensor") from oe

    return dht_sensor


def get_temperature_and_humidity(sensor: dht.DHT11):
    try:
        sensor.measure()
        temperature = sensor.temperature()
        time.sleep(1)
        humidity = sensor.humidity()
        return temperature, humidity
    except OSError as e:
        print("Error reading DHT11 sensor:", e)
        return None, None


def set_influxdb_headers(config):
    influxdb_config = config.get("influxdb", {})
    return {
        "Authorization": f"Token {influxdb_config.get('token')}",
        "Content-Type": "text/plain; charset=utf-8",
        "Accept": "application/json",
    }


def get_influxdb_url(config):
    influxdb_config = config.get("influxdb", {})
    url_params = {
        "host": influxdb_config.get("host", "localhost"),
        "port": influxdb_config.get("port", 8086),
        "bucket": influxdb_config.get("bucket"),
        "org": influxdb_config.get("org"),
    }
    return "{host}:{port}/api/v2/write?org={org}&bucket={bucket}&precision=ns".format(
        **url_params
    )


def send_to_influxdb(url, headers, data) -> None:
    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 204:
        print("Data sent to InfluxDB")
    else:
        print("Failed to send data to InfluxDB")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")

    return


if __name__ == "__main__":

    # Load configuration from file
    config = load_config("config.json")

    # Extract WiFi configuration from the loaded config
    wifi_config = config.get("wifi", {})

    # Connect to WiFi network
    if connect_to_wifi(wifi_config.get("ssid"), wifi_config.get("key")):
        print("WiFi connected successfully.")
        wlan = network.WLAN(network.STA_IF)
        print(f"Network config: {wlan.ifconfig()}")
    else:
        print("Failed to connect to WiFi. Exiting...")
        sys.exit(1)

    # Setup InfluxDB headers and URL
    headers = set_influxdb_headers(config)
    influxdb_url = get_influxdb_url(config)

    # Initialize DHT sensor
    sensor = init_dht_sensor(4)

    # Main loop for reading sensor data and sending to InfluxDB
    while True:

        temperature, humidity = get_temperature_and_humidity(sensor)
        if all([temperature is not None, humidity is not None]):
            # Prepare data string
            data = f"dht_sensor,sensor_id=esp8266 temperature={temperature:.1f},humidity={humidity:.1f}"
            print("Data:", data)

            # Send data to InfluxDB
            send_to_influxdb(influxdb_url, headers, data)

        # Get wait time from configuration or use default
        wait_time = config.get("reading_wait_time", DEFAULT_WAIT_TIME)
        time.sleep(wait_time)
