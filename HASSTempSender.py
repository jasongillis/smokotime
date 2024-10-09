# HTTP server code developed from https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

import time

import json

import sys
from datetime import datetime
from requests import post, get
from requests.exceptions import SSLError
from requests.exceptions import ConnectionError
from requests.exceptions import ReadTimeout
from requests.exceptions import ConnectTimeout

from Temp import TempMeasurement

from pprint import pprint

class HASSTempSender:
    def __init__(self, server: str, port: int, token: str):
        self.server = server
        self.token = token
        self.port = port
        self._enabled = True

    @property
    def entity(self) -> str:
        return self._entity

    @entity.setter
    def entity(self, entity_name: str):
        self._entity = entity_name

    def enable(self):
        """Enable switch control"""
        self._enabled = True

    def disable(self):
        """Disable switch control and turn the switch off"""
        self.switch('off')
        self._enabled = False

    def headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'content-type': 'application/json',
            'Connection': 'close'
        }

    def switch(self, action: str):
        """Issue HASS command (on or off) for the entity"""
        if self._enabled:
            print(f'HASSTempSender {self.entity} action {action}')
            url = f'https://{self.server}:{self.port}/api/services/switch/turn_{action}'
            try:
                response = post(url,
                                headers=self.headers(),
                                data=json.dumps( { "entity_id": self.entity } ),
                                verify='/home/pi/cacert.pem',
                                timeout=(10,120)
                                )
                # print(f'Response code = {response.status_code}')
                status_code = int(response.status_code)
                if status_code >= 300 or status_code < 200:
                    print(f'Error calling HASS API: {url}')
                    print('-------------')
                    print(response.text)
                    print('-------------')
            except Exeption as e:
                print(f'############## Error calling switch API:  {url}:')
                print(e)
                pass

    def get_switch_state(self):
        """Retrieve the switch's current state from HASS"""
        # print(f'HASSTempSender {self.entity} state')

        url = f'https://{self.server}:{self.port}/api/states/{self.entity}'
        try:
            response = get(url,
                           headers=self.headers(),
                           verify='/home/pi/cacert.pem',
                           timeout=(10,120)
                           )
            # print(f'Response code = {response.status_code}')
            status_code = int(response.status_code)
            if status_code >= 200 or status_code < 300:
                data = json.loads(response.text)
                # print('Data:')
                # pprint(data)
                # print(f'State of {self.entity} is {data["state"]}')
                return data['state']
            else:
                print(f'Error calling HASS API: {url}')
                print('-------------')
                print(response.text)
                print('-------------')
        except Exception as e:
            print(f'############## Error calling state API:  {url}:')
            print(e)
            pass

    @property
    def sensor(self) -> str:
        return self._sensor

    @sensor.setter
    def sensor(self, sensor_name: str):
        self._sensor = sensor_name

    def publish(self, latest_data: TempMeasurement):
        """Publish sensor data to the defined sensor in HASS"""
        now = datetime.now().isoformat()
        payloads = [
            [ f'sensor.{self.sensor}_c', {
                'state': "{:.1f}".format(latest_data.temp),
                'attributes': {
                    'unit_of_measurement': '°C',
                    'friendly_name': 'Smoker Temp C',
                    'datetime': now
                } } ],
            [ f'sensor.{self.sensor}_f', {
                'state': "{:.1f}".format((latest_data.temp * 1.8) + 32.0),
                'attributes': {
                    'unit_of_measurement': '°F',
                    'friendly_name': 'Smoker Temp F',
                    'datetime': now
                } } ],
            [ f'sensor.{self.sensor}_delta_c', {
                'state': "{:.1f}".format(latest_data.delta),
                'attributes': {
                    'unit_of_measurement': '°C',
                    'friendly_name': 'Smoker Temp Delta C',
                    'datetime': now
                } } ],
            [ f'sensor.{self.sensor}_delta_f', {
                'state': "{:.1f}".format((latest_data.delta * 1.8)),
                'attributes': {
                    'unit_of_measurement': '°F',
                    'friendly_name': 'Smoker Temp Delta F',
                    'datetime': now
                } } ],
            [ f'sensor.{self.sensor}_target_c', {
                'state': "{:.1f}".format(latest_data.target_temp),
                'attributes': {
                    'unit_of_measurement': '°C',
                    'friendly_name': 'Smoker Temp Target C',
                    'datetime': now
                } } ],
            [ f'sensor.{self.sensor}_target_f', {
                'state': "{:.1f}".format((latest_data.target_temp * 1.8) + 32.0),
                'attributes': {
                    'unit_of_measurement': '°F',
                    'friendly_name': 'Smoker Temp Target F',
                    'datetime': now
                } } ]

            ]
        connection_errors = 0
        other_errors = 0
        connect_timeouts = 0
        read_timeouts = 0
        os_errors = 0
        payload_count = 0

        for payload in payloads:
            try:
                #print('.')
                response = post(f'https://{self.server}:{self.port}/api/states/' + payload[0],
                                headers=self.headers(),
                                data=json.dumps(payload[1]),
                                verify='/home/pi/cacert.pem',
                                timeout=(10,120))
                if response.status_code != 200:
                    print(f'Status Code: {response.status_code} - {response.reason}')
                    print('----------')
                    print(response.text)
                    print('----------')
                # print('Request: {}\n{}: {}'.format(json.dumps(payload[1]), response.status_code, response.text))
                payload_count = payload_count + 1
                # print(response.text)
            except ConnectionError as err:
                print('New Connection Error: {}'.format(err))
                connection_errors = connection_errors + 1
                pass
            except ReadTimeout as err:
                print('Connect Timeout: {}'.format(err))
                connect_timeouts = connect_timeouts + 1
                pass
            except ConnectTimeout as err:
                print('Read Timeout: {}'.format(err))
                read_timeouts = read_timeouts + 1
                pass
            except SSLError as err:
                print('SSL Error:  {}'.format(err))
                ssl_errors = ssl_errors + 1
                pass
            except OSError as err:
                print('OS Error:  {}'.format(err))
                os_errors = os_errors + 1
                pass
            except:
                print('########### Error encountered:  {}'.format(sys.exc_info()[0]))
                # Continue on and try again
                other_errors = other_errors + 1
                pass
