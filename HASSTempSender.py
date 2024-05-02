# HTTP server code developed from https://medium.com/@andrewklatzke/creating-a-python3-webserver-from-the-ground-up-4ff8933ecb96

import time

import json

import sys
from datetime import datetime
from requests import post
from requests.exceptions import SSLError
from requests.exceptions import ConnectionError
from requests.exceptions import ReadTimeout
from requests.exceptions import ConnectTimeout


class HASSTempSender:
    def __init__(self, server: str, port: int, token: str):
        self.server = server
        self.token = token
        self.port = port

    def headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'content-type': 'application/json',
            'Connection': 'close'
        }

    def switch(self, entity_id: str, action: str):
        url = f'https://{self.server}:{self.port}/api/services/switch/turn_{action}'
        try:
            response = post(url,
                            headers=self.headers(),
                            data=json.dumps( { "entity_id": entity_id } ),
                            verify='/home/pi/cacert.pem',
                            timeout=(10,120)
                            )
            if response.status_code != 200:
                print(f'Error calling HASS API: {url}')
                print('-------------')
                print(response.text)
                print('-------------')
        except:
            print('############## Error calling API:  {}'.format(sys.exc_info()[0]))
            pass

    def publish(self, sensor_name, temp_c):
        now = datetime.now().isoformat()
        payloads = [
            [ f'sensor.{sensor_name}_c', {
                'state': "{:.1f}".format(temp_c),
                'attributes': {
                    'unit_of_measurement': '°C',
                    'friendly_name': 'Smoker Temp C',
                    'datetime': now
                } } ],
            [ f'sensor.{sensor_name}_f', {
                'state': "{:.1f}".format((temp_c * 1.8) + 32.0),
                'attributes': {
                    'unit_of_measurement': '°F',
                    'friendly_name': 'Smoker Temp F',
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
