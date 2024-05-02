# HTTP server code developed from https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

from datetime import datetime
import board
import digitalio
import adafruit_max31856
from adafruit_max31856 import ThermocoupleType
from enum import Enum

import numpy as np
from numpy.polynomial import Polynomial

import time
import threading
import json

from MQTTPublisher import MQTTPublisher
from HASSTempSender import HASSTempSender

class SmokerMonitor:
    def __init__(self,
                 mqtt_server: str,
                 hass_server: str,
                 hass_token: str,
                 mqtt_user: str,
                 mqtt_pass: str,
                 target_temp: float=25.0,
                 target_delta: float=2.5,
                 mqtt_port: int=1883,
                 hass_port: int=8123):
        print('Initializing the smoker temperature monitor')
        self.mqtt_server = mqtt_server
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass
        print('Creating a MQTT publisher')
        self.mqtt_switch = 'SNF-Plug7'
        self.mqtt_publisher = MQTTPublisher(self.mqtt_server, self.mqtt_port, self.mqtt_user, self.mqtt_pass)

        self.hass_server = hass_server
        self.hass_port = hass_port
        self.hass_token = hass_token
        print('Creating a Home Assistant sender')
        self.hass_sensor = 'smoker_temp'
        self.entity_id = 'switch.snf_plug7'
        self.hass_sender = HASSTempSender(self.hass_server, self.hass_port, self.hass_token)

        print('Initializing the thermocouple')
        self.thermocouple_init = False
        self.init_thermocouple()

        self.monitoring_state = 'Stopped'
        self.stop_monitoring = False
        # Number of times per minute to operate
        self.monitoring_interval = 10
        self.heating_state = 'off'
        self.new_heating_state = ''

        self.latest_temp = -1
        self._temp_history = []
        self.target_temp = target_temp
        self.target_delta = target_delta

        self.monitor_thread = None
        self.tracking_thread = None
        self.heater_thread = None

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @entity_id.setter
    def entity_id(self, state: str):
        self._entity_id = state

    @property
    def heating_state(self) -> str:
        return self._heating_state

    @heating_state.setter
    def heating_state(self, state: str):
        self._heating_state = state

    @property
    def new_heating_state(self) -> str:
        return self._new_heating_state

    @new_heating_state.setter
    def new_heating_state(self, state: str):
        self._new_heating_state = state

    @property
    def monitoring_interval(self) -> int:
        return self._monitoring_interval

    @monitoring_interval.setter
    def monitoring_interval(self, state: int):
        self._monitoring_interval = state

    @property
    def monitoring_state(self) -> str:
        return self._monitoring_state

    @monitoring_state.setter
    def monitoring_state(self, new_state: str):
        self._monitoring_state = new_state

    @property
    def mqtt_publisher(self) -> MQTTPublisher:
        return self._mqtt_publisher

    @mqtt_publisher.setter
    def mqtt_publisher(self, publisher: MQTTPublisher):
        self._mqtt_publisher = publisher

    @property
    def mqtt_switch(self) -> str:
        return self._mqtt_switch

    @mqtt_switch.setter
    def mqtt_switch(self, switch_name: str):
        self._mqtt_switch = switch_name

    @property
    def hass_sender(self) -> HASSTempSender:
        return self._hass_sender

    @hass_sender.setter
    def hass_sender(self, sender: HASSTempSender):
        self._hass_sender = sender

    @property
    def hass_sensor(self) -> str:
        return self._hass_sensor

    @hass_sensor.setter
    def hass_sensor(self, sensor_name: str):
        self._hass_sensor = sensor_name

    @property
    def target_temp(self):
        """Return the target temperature in degrees C"""
        return (1.8*self._target_temp + 32.0)

    @target_temp.setter
    def target_temp(self, target_temp: float):
        """Update the target temperature in degrees C"""
        self._target_temp = ((target_temp - 32.0) * (5.0/9.0))

    @property
    def target_delta(self):
        """Return the target temperature delta in degrees C"""
        return self._target_delta

    @target_delta.setter
    def target_delta(self, target_delta):
        self._target_delta = target_delta

    @property
    def latest_temp(self) -> float:
        return self._latest_temp

    @latest_temp.setter
    def latest_temp(self, latest_temp:float):
        self._latest_temp = latest_temp

    @property
    def temp_history(self):
        return self._temp_history

    def add_temp_reading(self, temp):
        one_min_temp = temp
        if len(self._temp_history) >= self.monitoring_interval:
            one_min_temp = self.one_min_temp()

        self._temp_history.append({
            'time': datetime.now(),
            'temperature': temp,
            'set_temperature': self.target_temp,
            'delta': self.target_delta,
            'one_min_temp': one_min_temp
        })
        # print(json.dumps(self._temp_history, default=str))

    @property
    def monitoring_state(self) -> str:
        return self._monitoring_state

    @monitoring_state.setter
    def monitoring_state(self, new_state: str):
        self._monitoring_state = new_state

    def init_thermocouple(self) -> bool:
        if not self.thermocouple_init:
            spi = board.SPI()
            cs = digitalio.DigitalInOut(board.D5)
            cs.direction = digitalio.Direction.OUTPUT

            self.thermocouple = adafruit_max31856.MAX31856(spi, cs, thermocouple_type=ThermocoupleType.K)
            self.thermocouple.averaging = 4

            self.thermocouple_init = True

        if self.thermocouple_init == False:
            print('Error initializing the thermocouple')
        else:
            print('Initial temperature from the thermocouple is {self.thermocouple.temperature}')

        return self.thermocouple_init

    def start_temp_monitor(self):
        # Don't do anything if the thermocouple isn't initialized
        print('Starting temperature monitoring')
        if self.thermocouple_init == False:
            self.monitoring_state = 'Failed (Thermocouple)'
            return

        self._temp_history = []
        self.stop_monitoring = False
        self.monitoring_state = 'Starting'
        self.monitor_thread = threading.Thread(target=self.monitor_temp)
        self.monitor_thread.start()

        self.tracking_thread = threading.Thread(target=self.temp_tracker)
        self.tracking_thread.start()

        self.heater_thread = threading.Thread(target=self.heater)
        self.heater_thread.start()

    def stop_temp_monitor(self):
        """Ask the monitoring thread to stop and wait for it to finish."""
        print('Stopping temperature monitoring')
        self.stop_monitoring = True
        self.monitoring_state = 'Stopping'

        if self.monitor_thread is not None:
            self.monitor_thread.join()
        if self.tracking_thread is not None:
            self.tracking_thread.join()
        if self.heater_thread is not None:
            self.heater_thread.join()

        self.monitoring_state = 'Stopped'

    def monitor_temp(self):
        """Thread to continuously gather temperature data from the thermocouple.  No decision making."""
        while True:
            if self.stop_monitoring:
                break
            temp = 0.5 * round(self.thermocouple.temperature/0.5)
            print(f'Last temp was {temp}')
            self.add_temp_reading(temp)
            time.sleep(60/self.monitoring_interval)

    def one_min_temp(self):
        if len(self.temp_history) >= self.monitoring_interval:
            # find the expected temp after one minute.  Must
            # be one min of readings.
            x_vals = np.arange(0,self.monitoring_interval)
            print(f'len(self.temp_history) = {len(self.temp_history)}  -- self.monitoring_interval == {self.monitoring_interval}')
            last_readings = list(map(lambda x: x['temperature'], self.temp_history[-self.monitoring_interval:]))
            # Get the polynomial for the last minute
            p = Polynomial.fit(x_vals, last_readings, 1, window=[0,self.monitoring_interval])

            return p(self.monitoring_interval * 2)
        else:
            return -1

    def heater(self):
        """Tight loop to turn the heat switch on and off"""
        while True:
            if self.stop_monitoring:
                return

            if self.new_heating_state != '':
                if self.heating_state == 'off' and self.new_heating_state == 'on':
                    print('+')
                    self.hass_sender.switch(self.entity_id, 'on')
                    self.heating_state = 'on'
                elif self.heating_state == 'on' and self.new_heating_state == 'off':
                    print('-')
                    self.hass_sender.switch(self.entity_id, 'off')
                    self.heating_state = 'off'

            time.sleep(1)

    def temp_tracker(self):
        """Thread to drive tracking of temperature and controlling the smoker switch"""
        class SmokerState(Enum):
            OFF = 0
            INIT = 1
            PREHEAT = 2
            COOKING = 3

        current_state = SmokerState.INIT

        # Wait for enough monitoring data to be present.  Should be
        # one minute.
        while len(self.temp_history) <= self.monitoring_interval:
            if self.stop_monitoring:
                return
            time.sleep(60/self.monitoring_interval)

        while True:
            if self.stop_monitoring:
                return

            now_temp = self.latest_temp
            one_min_temp = self.one_min_temp()
            print(f'Temp in one min = {one_min_temp}')
            print(f'Target range = {self.target_temp - self.target_delta} to {self.target_temp + self.target_delta}')

            # if the one min temp is below the range, then turn on the element
            if one_min_temp <= self.target_temp - self.target_delta:
                self.new_heating_state = 'on'

            # otherwise turn it off and see what happens
            if one_min_temp >= self.target_temp - self.target_delta:
                self.new_heating_state = 'off'

            time.sleep(60/self.monitoring_interval)

################################################################################
################################################################################
################################################################################
################################################################################


    def heat_on(self, duration: int, cooldown: int):
        self.heating_mode = 'heating'
        self.hass_sender.switch(self.entity_id, 'on')
        #self.mqtt_publisher.publish(f'{self.mqtt_switch}/cmnd/power', 'ON')
        time.sleep(duration)
        self.hass_sender.switch(self.entity_id, 'off')
        # self.mqtt_publisher.publish(f'{self.mqtt_switch}/cmnd/power', 'OFF')
        self.heating_mode = 'cooldown'
        time.sleep(cooldown)
        self.heating_mode = 'off'


    def monitor_temp_old(self):
        def halfround(x, base=0.5):
            return base * round(x/base)

        print('Initializing monitoring thread...')

        self._temp_history = []
        # self.debug_add_temp_data()

        index = 0
        intervals = 4
        while True:
            if self.stop_monitoring:
                break

            # The thermocouple has an accuracy of 0.5 deg C, round the
            # result
            temp = halfround(self.thermocouple.temperature, base=0.5)
            print(f'[{index}] Temperature = {temp}')

            # Wait five minutes before acting on any temperature data
            # to let the probe readings settle.
            if index > 2:
                self.monitoring_state = 'Monitoring'
                # Record the temperature
                self.add_temp_reading(temp)



                next_temp = (temp - self.latest_temp) + temp
                print(f'[{index}] Predicted temperature:  {next_temp}')
                print(f'[{index}] Range: {self.target_temp - self.target_delta} <= {self.target_temp} <= {self.target_temp + self.target_delta}')
                if next_temp >= (self.target_temp + self.target_delta):
                    print(f'[{index}] Predicted is greater than range, so should turn off')

                if temp <= (self.target_temp - self.target_delta):
                    # Turn on the switch
                    print('Switch on...')
                    self.mqtt_publisher.publish(f'{self.mqtt_switch}/cmnd/power', 'ON')

                if (temp >= (self.target_temp + self.target_delta)) or (next_temp >= (self.target_temp + self.target_delta)) :
                    # Turn off the switch
                    print('Switch off...')
                    self.mqtt_publisher.publish(f'{self.mqtt_switch}/cmnd/power', 'OFF')

                # Publish to Home Assistant every minute
                if index % 4 == 0:
                    self.hass_sender.publish(self.hass_sensor, temp)
                    print(' +')

            self.latest_temp = temp
            print('')
            index += 1
            time.sleep(15)

    def join(self):
        self.monitor_thread.join()

# mqtt_server = 'server.house'
# mqtt_user = 'mqttdev'
# mqtt_pass = '***REMOVED***'
# hass_server = 'server.house'
# hass_token = "***REMOVED***"
# sm = SmokerMonitor(mqtt_server, hass_server, hass_token, mqtt_user, mqtt_pass, target_temp = 250.0, target_delta = 2.5)
# sm.start_temp_monitor()
# sm.join()







# # Create sensor object, communicating over the board's default SPI bus
# spi = board.SPI()

# # allocate a CS pin and set the direction
# cs = digitalio.DigitalInOut(board.D5)
# cs.direction = digitalio.Direction.OUTPUT

# # create a thermocouple object with the above
# # The thermoworks probe has a accuracy of 0.5 C and requires about 10s to read properly.
# # Average four results to get a response on the reading, too.
# thermocouple = adafruit_max31856.MAX31856(spi, cs, thermocouple_type=ThermocoupleType.K)
# thermocouple.averaging = 4


# hass = HASSTempSender('server.house', 8123, token)


# # print the temperature!
# index = 0
# x = []
# y = []
# while True:
#     temp = halfround(thermocouple.temperature)
#     print(f'The temperature[{index}] = {temp}', end='')
#     if index % 6 == 0:
#         print(' +')
#         hass.publish(temp)
#     else:
#         print('')
#     x.append(index)
#     y.append(temp)
#     index += 1
#     time.sleep(10)

# def PolyCoeff(x, p):
#     return p(x)
#     # y = []
#     # for val in x:
#     #     y.append(p(val))

#     # print('Returning:  ', end='')
#     # print(y)

#     # return y

# p1 = Polynomial.fit(x, y, 1, window=[0,index])
# p2 = Polynomial.fit(x, y, 2, window=[0,index])
# p3 = Polynomial.fit(x, y, 3, window=[0,index])
# print("Polynomial degree 1:  ", end='')
# print(p1)
# print("Polynomial degree 2:  ", end='')
# print(p2)
# print("Polynomial degree 3:  ", end='')
# print(p3)

# for max_range in range(2, 20):
#     print('================================================')
#     print(f'max_range = {max_range}')
#     x = np.arange(max_range)
#     y = list(map(lambda x: x**3 + 45.5 * x**2 + 126 * x - 36, x))

#     #print(x)
#     #print(y)

#     p = Polynomial.fit(x, y, 3, window=[0,max_range])
#     # print(p)
#     space = np.linspace(0,99,100)
#     if max_range % 4000 == 0:
#         plt.plot(space, PolyCoeff(space, p), label=f'Series {max_range}')
#         plt.xlim(0,99)


# mqtts = MQTTPublisher('172.16.0.126', 1883, 'mqttdev', '***REMOVED***')

# mqtts.connect()

# time.sleep(5)

# mqtts.publish(

# mqtt.disconnect()
