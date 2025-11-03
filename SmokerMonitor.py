# HTTP server code developed from https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

from datetime import datetime
import pytz

import board
import digitalio
import adafruit_max31856
from adafruit_max31856 import ThermocoupleType
from enum import Enum

import time
import threading
import json

# from MQTTPublisher import MQTTPublisher
from HASSTempSender import HASSTempSender
from Temp import TempHistory


class SmokerMonitor:
    def __init__(self,
                 # mqtt_server: str,
                 hass_server: str,
                 hass_token: str,
                 # mqtt_user: str,
                 # mqtt_pass: str,
                 target_temp: float=25.0,
                 target_delta: float=2.5,
                 # mqtt_port: int=1883,
                 hass_port: int=8123):
        print('Initializing the smoker temperature monitor')

        print('Initialing the HASS sender...')
        self.init_hass_sender(hass_server, hass_token, hass_port)

        print('Initializing the thermocouple')
        self.thermocouple_init = False
        self.init_thermocouple()

        print('Creating the temp history object')
        self._temp_history = TempHistory(target_temp, target_delta, units='C')

        self.monitoring_state = 'Stopped'
        self.action = 'Start'
        self.stop_monitoring = False
        # Number of times per minute to operate
        self.monitoring_interval = 10
        self.heating_state = 'off'
        self.heating_state = self.hass_sender.get_switch_state()
        self.new_heating_state = ''

        self.monitor_thread = None
        self.tracking_thread = None
        self.heater_thread = None

        self.disable()

        # parameters used for the PID control model
        self._proportional_gain = 0.5
        self._integral_gain = 0.01
        self._derivative_gain = 1.0
        self._alpha = 0.1
        self._integral_windup_guard = 5.0

    def enable(self):
        self._enabled = True
        self._hass_sender.enable()

    def disable(self):
        self._enabled = False
        self._hass_sender.disable()

    @property
    def enabled(self):
        return self._enabled

    ########################### HASS Related #################################
    @property
    def hass_sender(self) -> HASSTempSender:
        return self._hass_sender

    @hass_sender.setter
    def hass_sender(self, sender: HASSTempSender):
        self._hass_sender = sender

    @property
    def hass_entity(self) -> str:
        return self.hass_sender.entity

    @hass_entity.setter
    def hass_entity(self, state: str):
        self.hass_sender.entity = state

    @property
    def hass_sensor(self) -> str:
        return self.hass_sender.sensor

    @hass_sensor.setter
    def hass_sensor(self, sensor_name: str):
        self.hass_sender.sensor = sensor_name

    def init_hass_sender(self, hass_server, hass_token, hass_port=8123):
        print('Creating a Home Assistant sender')

        self.hass_sender = HASSTempSender(hass_server, hass_port, hass_token)

        self.hass_sender.sensor = 'smoker_temp'
        self.hass_sender.entity = 'switch.snf_plug7'
        self.disable_hass_sensor()

    @property
    def hass_sensor_enabled(self):
        return self._hass_sensor_enabled

    def enable_hass_sensor(self):
        self._hass_sensor_enabled = True

    def disable_hass_sensor(self):
        self._hass_sensor_enabled = False

    ############################## Heating ##############################
    @property
    def heating_state(self) -> str:
        if not self._enabled:
            return "disabled"
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
    def monitoring_interval(self, interval: int):
        self._temp_history.interval = interval
        self._monitoring_interval = interval

    @property
    def monitoring_state(self) -> str:
        return self._monitoring_state

    @monitoring_state.setter
    def monitoring_state(self, new_state: str):
        self._monitoring_state = new_state

    @property
    def temp_history(self):
        return self._temp_history

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
            print(f'Initial temperature from the thermocouple is {self.thermocouple.temperature}')

        return self.thermocouple_init

    def thermocouple_details(self):
        """Report back the details of the thermocouple in a dict structure"""
        raw_type = self.thermocouple._read_register(adafruit_max31856._MAX31856_CR1_REG, 1)[0]
        raw_type &= 0x0F

        type = 'K'
        if raw_type == ThermocoupleType.B:
            type = 'B'
        elif raw_type == ThermocoupleType.E:
            type = 'E'
        elif raw_type == ThermocoupleType.J:
            type = 'J'
        elif raw_type == ThermocoupleType.K:
            type = 'K'
        elif raw_type == ThermocoupleType.N:
            type = 'N'
        elif raw_type == ThermocoupleType.R:
            type = 'R'
        elif raw_type == ThermocoupleType.S:
            type = 'S'
        elif raw_type == ThermocoupleType.T:
            type = 'T'
        elif raw_type == ThermocoupleType.G8:
            type = 'G8'
        elif raw_type == ThermocoupleType.G32:
            type = 'G32'
        else:
            type = 'K'

        return {
            'type': type,
            'temp': self.thermocouple.temperature,
            'temp_thresholds': self.thermocouple.temperature_thresholds,
            'ref_temp': self.thermocouple.reference_temperature,
            'ref_temp_thresholds': self.thermocouple.reference_temperature_thresholds,
            'faults': self.thermocouple.fault
        }

    def start_temp_monitor(self):
        # Don't do anything if the thermocouple isn't initialized
        print('Starting temperature monitoring')
        if self.thermocouple_init == False:
            self.monitoring_state = 'Failed (Thermocouple)'
            self.action = ''
            return

        # self._temp_history = []
        # self.temp_index = 0
        self._temp_history.clear()

        self.stop_monitoring = False
        self.monitoring_state = 'Starting'
        self.action = 'Stop'
        self.monitor_thread = threading.Thread(target=self.monitor_temp)
        self.monitor_thread.start()

        # self.tracking_thread = threading.Thread(target=self.temp_tracker)
        self.tracking_thread = threading.Thread(target=self.pid_control)
        self.tracking_thread.start()

        self.heater_thread = threading.Thread(target=self.heater)
        self.heater_thread.start()

    def stop_temp_monitor(self):
        """Ask the monitoring thread to stop and wait for it to finish."""
        print('Stopping temperature monitoring')
        self.stop_monitoring = True
        self.monitoring_state = 'Stopping'
        self.action = 'Stop'

        if self.monitor_thread is not None:
            self.monitor_thread.join()
        if self.tracking_thread is not None:
            self.tracking_thread.join()
        if self.heater_thread is not None:
            self.heater_thread.join()

        self.monitoring_state = 'Stopped'
        self.action = 'Start'

    def monitor_temp(self):
        """Thread to continuously gather temperature data from the thermocouple.  No decision making."""
        while True:
            if self.stop_monitoring:
                break
            temp = 0.1 * round(self.thermocouple.temperature/0.1)
            # print(f'{datetime.now()}:  Last temp was {temp}')

            self._temp_history.add_temp_reading(temp, self.heating_state)
            if self.hass_sensor_enabled:
                self.hass_sender.publish(self._temp_history.latest)

            time.sleep(60/self.monitoring_interval)
            # time.sleep(1)

    def heater(self):
        """Tight loop to turn the heat switch on and off"""
        count = 1
        while True:
            if self.stop_monitoring:
                return

            # Refresh the state from HASS every 10 seconds
            if count % 10 == 0:
                self.heating_state = self.hass_sender.get_switch_state()
                count = 0

            count = count + 1

            if self.new_heating_state != '':
                if self.heating_state == 'off' and self.new_heating_state == 'on':
                    print('+')
                    self.hass_sender.switch('on')
                    self.heating_state = 'on'
                elif self.heating_state == 'on' and self.new_heating_state == 'off':
                    print('-')
                    self.hass_sender.switch('off')
                    self.heating_state = 'off'

            time.sleep(1)

    @property
    def proportional_gain(self):
        return self._proportional_gain

    @proportional_gain.setter
    def proportional_gain(self, new_gain):
        self._proportional_gain = new_gain

    @property
    def integral_gain(self):
        return self._integral_gain

    @integral_gain.setter
    def integral_gain(self, new_gain):
        self._integral_gain = new_gain

    @property
    def derivative_gain(self):
        return self._derivative_gain

    @derivative_gain.setter
    def derivative_gain(self, new_gain):
        self._derivative_gain = new_gain

    @property
    def alpha(self):
        return self._alpha

    @alpha.setter
    def alpha(self, new_alpha):
        self._alpha = new_alpha

    @property
    def integral_windup_guard(self):
        return self._integral_windup_guard

    @integral_windup_guard.setter
    def integral_windup_guard(self, new_guard):
        self._integral_windup_guard = new_guard


    def pid_control(self):
        # Time interval
        dt = self.monitoring_interval

        # Initialize terms
        previous_error = 0
        integral = 0
        previous_filtered_derivative = 0

        print('--- Waiting for some iterations')
        time.sleep(20)

        delay_on = 45
        delay_off = 60
        on_delay_buffer = [0] * delay_on
        off_delay_buffer = [0] * delay_off

        while True:
            if self.stop_monitoring:
                self.monitoring_state = 'Stopping'
                return

            self.monitoring_state = 'Started'

            # Setpoint
            T_set = self._temp_history.target_temp  # Desired temperature in degrees

            # PID parameters - pull these at every loop to account for
            # changes from the GUI
            K_p = self.proportional_gain
            K_i = self.integral_gain
            K_d = self.derivative_gain
            alpha = 0.1  # Smoothing factor for the derivative

            # Read the current temperature
            T_current = self._temp_history.latest_temp

            # Calculate the error
            error = T_set - T_current

            # Update the integral term
            integral += error * dt
            if integral > self.integral_windup_guard:
                integral = self.integral_windup_guard
            elif integral < -self.integral_windup_guard:
                integral = -self.integral_windup_guard

            # Calculate the derivative term
            derivative = (error - previous_error) / dt
            filtered_derivative = alpha * derivative + (1 - alpha) * previous_filtered_derivative

            # Compute the control output
            output = K_p * error + K_i * integral + K_d * filtered_derivative

            print(f'--- {T_set:3.2f}, {T_current:3.2f}, {error:3.2f}, {integral:5.2f}, {derivative:.2f}, {filtered_derivative:.2f}, -- {output:5.2f} -- {"on" if output > 0 else "off"} -- [ {K_p:.2f}, {K_i:.2f}, {K_d:.2f}, {alpha:.2f} ]')
            # print('on_db :  ' + ''.join(str(x) for x in on_delay_buffer))
            # print('off_db:  ' + ''.join(str(x) for x in off_delay_buffer))

            if output > 0:
                self.new_heating_state = 'on'
            else:
                self.new_heating_state = 'off'

            # if output > 0:
            #     on_delay_buffer.pop(0)
            #     on_delay_buffer.append(1)
            #     off_delay_buffer.pop(0)
            #     off_delay_buffer.append(0)
            # else:
            #     off_delay_buffer.pop(0)
            #     off_delay_buffer.append(1)
            #     on_delay_buffer.pop(0)
            #     on_delay_buffer.append(0)

            # # Apply the control output
            # if sum(on_delay_buffer) > 0 or sum(off_delay_buffer) > 0:
            #     self.new_heating_state = 'on'
            #     # control_heater(True)
            # else:
            #     self.new_heating_state = 'off'
            #     # control_heater(False)

            # Update the previous terms
            previous_error = error
            previous_filtered_derivative = filtered_derivative

            # Wait for the next control loop
            time.sleep(dt)

    def temp_tracker_new(self):
        # Function to return the future temperature if the element was
        # switched off now
        def off_temp_future(seconds) -> float:
            otf_p = Polynomial([ 4.44396492e-02,  1.72648956e-01,
                                 3.46405419e-02, -4.72060705e-03,
                                 3.33432101e-04, -1.37487099e-05,
                                 3.45755350e-07, -5.38467573e-09,
                                 5.07568719e-11, -2.65617763e-13,
                                 5.93215803e-16])
            return otf_p(seconds)

        # Function to return the future temperature if the element was
        # switched on now.
        def on_temp_future(seconds) -> float:
            on_p = Polynomial([ 4.31409459e+00, -9.48679313e-01,
                                4.84294276e-02, -8.81005776e-04,
                                8.25270973e-06, -4.34859945e-08,
                                1.37213684e-10, -2.65498681e-13,
                                3.09097128e-16, -1.98933195e-19,
                                5.44196091e-23])
            return on_p(seconds)

        temp_now = self.temp_history.latest_temp

        range_low = self._temp_history.target_temp - self._temp_history.delta
        range_high = self._temp_history.target_temp + self.temp_history.delta

        if self.heating_state == 'on':
            # If the temp is already above, turn off the element
            if temp_now > range_high:
                self.new_heating_state = 'off'

            # If the element gets turned off now and will be in the
            # range in one minute, then turn off the element
            elif range_low <= (temp_now + off_temp_future(60)):
                self.new_heating_state = 'off'

            # If the temperature will still be below the range in 60
            # seconds, then keep it on.
            elif (temp_now + on_temp_future(60)) < range_low:
                self.new_heating_state = 'on'


    def temp_tracker(self):
        """Thread to drive tracking of temperature and controlling the
        smoker switch.  This runs every 60/interval seconds to check
        status."""

        class SmokerState(Enum):
            OFF = 0
            INIT = 1
            PREHEAT = 2
            COOKING = 3

        current_state = SmokerState.INIT

        # Wait for enough monitoring data to be present.  Should be
        # two minutes.
        while len(self.temp_history.temp_history) <= (2*self.monitoring_interval):
            pct_ready = int((len(self.temp_history.temp_history) / (2*self.monitoring_interval)) * 100)
            if self.stop_monitoring:
                return
            time.sleep(60/self.monitoring_interval)
            self.monitoring_state = f'Starting - {pct_ready}%'

        self.monitoring_state = 'Started'
        while True:
            if self.stop_monitoring:
                return

            now_temp = self._temp_history.latest_temp

            one_min_temp = self._temp_history.one_min_temp()
            print(f'Temp in one min = {one_min_temp}')
            range_low = self._temp_history.target_temp - self._temp_history.delta
            range_high = self._temp_history.target_temp + self.temp_history.delta
            print(f'Target range = {range_low} to {range_high}')

            # if the one min temp is below the range, then turn on the element
            if one_min_temp <= range_low:
                self.new_heating_state = 'on'

            # otherwise, if it's above the high range, turn it off and
            # see what happens
            if one_min_temp >= range_high:
                self.new_heating_state = 'off'

            time.sleep(60/self.monitoring_interval)
