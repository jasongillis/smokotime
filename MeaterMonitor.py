from datetime import datetime
import pytz

from meater import MeaterApi
import aiohttp
import asyncio

import time
import threading
import json

from pprint import pprint

# from MQTTPublisher import MQTTPublisher
from HASSTempSender import HASSTempSender
from Temp import TempHistory

class MeaterHistory:
    def __init__(self):
        self._index = 0
        self._measurements = {}
        self._cooks = {}

    @property
    def cooks(self):
        return self._cooks

    def add(self, meater_measurement):
        if not meater_measurement.cook.id in self._measurements:
            self._cooks[meater_measurement.cook.id] = meater_measurement.cook.name
            self._measurements[meater_measurement.cook.id] = []

        measurement = MeaterMeasurement(self._index, meater_measurement)
        self._measurements[meater_measurement.cook.id].append(measurement)
        self._index += 1

    @property
    def history(self):
        def f(v):
            return list(map(lambda x: x.data, v))

        return { k: f(v) for k, v in self._measurements.items() }

    def history_since(self, since_index):
        def f(v):
            filtered_items = filter(lambda x: x.index > since_index, v)
            return list(map(lambda x: x.data, filtered_items))

        return { k: f(v) for k, v in self._measurements.items() }

    def clear(self):
        self._index = 0
        self._measurements = {}
        self._cooks = {}


class MeaterMeasurement:
    def __init__(self, index, meater_measurement):
        meater_cook = meater_measurement.cook
        self._index = index
        self._internal = meater_measurement.internal_temperature
        self._ambient = meater_measurement.ambient_temperature
        self._time = meater_measurement.time_updated
        self._probe_id = meater_measurement.id
        self._cook_id = meater_cook.id
        self._cook_name = meater_cook.name
        self._state = meater_cook.state
        self._target_temp = meater_cook.target_temperature
        self._peak_temp = meater_cook.peak_temperature

        if hasattr(meater_cook, 'time_remaining'):
            self._remaining = meater_cook.time_remaining
        if hasattr(meater_cook, 'time_elapsed'):
            self._elapsed = meater_cook.time_elapsed

    @property
    def index(self):
        return self._index

    def __repr__(self):
        return str(self.data)

    @property
    def data(self):
        return {
            'index': self._index,
            'time': self._time,
            'timestamp_ms': self._time.timestamp()*1000,
            'cook_id': self._cook_id,
            'probe_id': self._probe_id,
            'internal': self._internal,
            'ambient': self._ambient,
            'name': self._cook_name,
            'state': self._state,
            'target_temp': self._target_temp,
            'peak_temp': self._peak_temp,
            'remaining': self._remaining,
            'elapsed': self._elapsed }


class MeaterMonitor:
    def __init__(self,
                 meater_user: str,
                 meater_pass: str,
                 monitoring_interval:int = 4):
        self.meater_user = meater_user
        self.meater_pass = meater_pass

        self._history = MeaterHistory()
        self._client_session = None
        self._authenticated = False
        self._meater_api = None
        self.monitoring_interval = monitoring_interval
        self._monitor_thread = None

    @property
    def monitoring_interval(self):
        return self._monitoring_interval

    # Meater only updates every 15 seconds, don't allow an interval
    # greater than 4 times per minute
    @monitoring_interval.setter
    def monitoring_interval(self, new_interval: int):
        if new_interval > 4:
            self._monitoring_interval = 4
        else:
            self._monitoring_interval = new_interval

    @property
    def history(self):
        return self._history

    @property
    def client_session(self):
        async def cli_sess():
            return aiohttp.ClientSession()

        if self._client_session is None:
            self._client_session = asyncio.run(cli_sess())

        return self._client_session

    @client_session.setter
    def client_session(self, session):
        self._client_session = session

    @property
    def authenticated(self):
        return self._authenticated

    @authenticated.setter
    def authenticated(self, new_status):
        self._authenticated = new_status

    @property
    def meater_api(self):
        return self._meater_api

    @meater_api.setter
    def meater_api(self, new_api):
        self._meater_api = new_api


    @property
    def monitoring(self) -> bool:
        return self._monitoring

    @monitoring.setter
    def monitoring(self, new_value: bool):
        self._monitoring = new_value

    def start(self):
        print('Starting the Meater monitor')
        if self._monitor_thread is not None:
            self.monitoring = False
            self._monitor_thread.join()

        self._history.clear()

        self.monitoring = True
        self._monitor_thread = threading.Thread(target=self.monitor_meater)
        self._monitor_thread.start()

    def stop(self):
        print('Stopping the Meater monitor')
        self.monitoring = False
        if self._monitor_thread is not None:
            self._monitor_thread.join()

    def monitor_meater(self):
        async def monitor():
            meater_api = None
            async with aiohttp.ClientSession() as session:
                if meater_api is None:
                    meater_api = MeaterApi(session)

                await meater_api.authenticate(self.meater_user,
                                              self.meater_pass)

                while True:
                    if self.monitoring == False:
                        break

                    await self.get_latest_temps(meater_api)

                    time.sleep(60/self.monitoring_interval)

        asyncio.run(monitor())

    async def get_latest_temps(self, meater_api):
        #     return await api.get_all_devices()

        # if not self.authenticated and self.authenticate():
        #     print("Unable to authenticate")
        #     return

        probes = await meater_api.get_all_devices()

        if len(probes) != 0:
            index = 0
            for probe in probes:
                if probe.cook is not None:
                    self._history.add(probe)
                    print('Meater temps')
                    pprint(probe.cook)
                index += 1
        else:
            print('No meater probes.  Is the block on and connected to WiFi?')
