from paho.mqtt import client as mqtt_client

import time

class MQTTPublisher:
    def __init__(self, broker: str, port: int, user: str, password: str):
        self.broker = broker
        self.port = port
        self.user = user
        self.password = password
        self.should_disconnect = False
        self.connected = False
        self.client = None

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f'Connected to {self.broker}:{self.port}')
            self.connected = True
        else:
            print(f'Failed to connect to {self.broker}:{self.port}:  {rc}')
            self.connected = False

    def on_disconnect(self, client, userdata, rc):

        FIRST_RECONNECT_DELAY = 1
        RECONNECT_RATE = 2
        MAX_RECONNECT_COUNT = 12
        MAX_RECONNECT_DELAY = 60

        self.connected = False

        if self.should_disconnect == True:
            print(f'Disconnected from {self.broker}:{self.port}.')
            self.client.loop_stop()
            return

        print("Disconnected with result code: %s", rc)
        reconnect_count, reconnect_delay = 0, FIRST_RECONNECT_DELAY
        while reconnect_count < MAX_RECONNECT_COUNT:
            print("Reconnecting in %d seconds...", reconnect_delay)
            time.sleep(reconnect_delay)

            try:
                client.reconnect()
                self.connected = True
                print("Reconnected successfully!")
                return
            except Exception as err:
                print("%s. Reconnect failed. Retrying...", err)

            reconnect_delay *= RECONNECT_RATE
            reconnect_delay = min(reconnect_delay, MAX_RECONNECT_DELAY)
            reconnect_count += 1

        print("Reconnect failed after %s attempts. Exiting...", reconnect_count)

    def connect(self):
        self.client = mqtt_client.Client('smoker.iot.house-mqtt')
        self.client.username_pw_set(self.user, self.password)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        print('Calling connect...')
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def disconnect(self):
        print(f'Disconnecting from {self.broker}:{self.port}')
        self.should_disconnect = True
        self.client.disconnect()

    def publish(self, topic: str, message: str):
        if self.client is None:
            self.connect()

        self.client.publish(topic, payload=message, retain=False)
