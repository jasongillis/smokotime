import numpy as np
from numpy.polynomial import Polynomial
from typing import Optional

from datetime import datetime
import pytz

class TempMeasurement:
    def __init__(self, index, temp, target_temp, temp_delta, units, one_min_temp, heating_state: str):
        self._index = index
        self._time = datetime.now(pytz.utc).astimezone()
        self._temp = temp
        self._target_temp = target_temp
        self._delta = temp_delta
        self._units = units
        self._one_min_temp = one_min_temp
        if heating_state == 'on':
            self._heating = 1
        else:
            self._heating = 0

    @property
    def index(self):
        return self._index

    @property
    def temp(self):
        return self._temp

    @property
    def time(self):
        return self._time

    @property
    def target_temp(self):
        return self._target_temp

    @property
    def delta(self):
        return self._delta

    @property
    def units(self):
        return self._units

    @property
    def one_min_temp(self):
        return self._one_min_temp

    @property
    def heating(self):
        return self._heating

    @property
    def data(self):
        return {
            'index': self.index,
            'time': self.time,
            'temperature': self.temp,
            'set_temperature': self.target_temp,
            'delta': self.delta,
            'units': self.units,
            'one_min_temp': self.one_min_temp,
            'heating': self.heating
        }

class TempHistory:
    def __init__(self, target_temp, delta, units='C'):
        self._measurements = []
        self._index = 0
        self._target_temp = target_temp
        self._delta = delta
        self._units = units

    def add_temp_reading(self, temp, heating_state='off'):
        one_min_temp = self.one_min_temp()
        measurement = TempMeasurement(self.current_index,
                                      temp,
                                      self._target_temp,
                                      self._delta,
                                      self._units,
                                      one_min_temp,
                                      heating_state)
        self._measurements.append(measurement)

    def clear(self):
        self._measurements = []
        self._index = 0

    @property
    def current_index(self):
        self._index = self._index + 1
        return self._index

    @property
    def target_temp(self):
        return self._target_temp

    @target_temp.setter
    def target_temp(self, new_temp):
        self._target_temp = new_temp

    @property
    def delta(self):
        return self._delta

    @delta.setter
    def delta(self, new_delta):
        self._delta = new_delta

    @property
    def latest_temp(self):
        return self._measurements[-1].temp

    @property
    def latest(self):
        return self._measurements[-1]

    @property
    def temp_history(self):
        return list(map(lambda x: x.data, self._measurements))

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, new_interval):
        self._interval = new_interval

    def temp_history_since(self, since_index):
        filtered_items = filter(lambda x: x.index > since_index, self._measurements)
        return list(map(lambda x: x.data, filtered_items))

    def one_min_temp(self):
        window_size = self.interval
        if len(self._measurements) >= window_size:
            # find the expected temp after one minute.  Must
            # be one min of readings.
            x_vals = np.arange(0, window_size)
            # print(f'len(self._measurements) = {len(self._measurements)} && self.interval == {self.interval}')
            last_readings = list(map(lambda x: x.temp, self._measurements[-(window_size):]))

            poly_order = 1

            # Get the polynomial for the last minute
            p = Polynomial.fit(x_vals,
                               last_readings,
                               poly_order,
                               window=[0,window_size])

            latest_reading = self._measurements[-1]

            # each multiplier of self.interval == 1 minute
            # 0 would be the start of the look back window, so
            # look ahead should be greater than that at least

            # Default is to look ahead 2 minutes
            look_ahead = 2 * self.interval

            # If the heating element is on, look ahead 3 minutes
            if latest_reading.heating == 1:
                # look three minutes ahead
                look_ahead = 2 * self.interval

            # Get the future value and return it
            future_value = p(look_ahead)

            return future_value
        else:
            return -1

    def last_heating_cycle(self):
        """Retrieve all the measurements in the last heating cycle."""
        end_index = -1
        length = 0

        for i in range(len(self._measurements) - 1, -1, -1):
            if self._measurements[i].heating == 1:
                if length == 0:
                    end_index = i
                length += 1
            elif length > 0:
                # heating off was found after seeing heating on
                break

        if length == 0:
            return []

        return self._measurements[end_index - length + 1:end_index + 1]

    def last_heating_tail(self):
        """Retrieve the sixty measurements following the end of the last heating cycle."""
        beg_index = -1
        length = 0

        # Find the end of the last heating cycle
        for i in range(len(self._measurements) - 1, -1, -1):
            if self._measurements[i].heating == 1:
                beg_index = i

        # retrieve the last minute, at most
        end_index = (beg_index + 60) if (beg_index + 60) <= len(self._measurements) else len(self._measurements)
        return self._measurement[beg_index:end_index]

    def generate_polynomial(self, measurements) -> Polynomial:
        x = [x for x in range(0,len(measurements))]
        y = [(x.temperature - cycle[0]['temperature']) for x in measurements]

        p = Polynomial.fit(x, y, 10, window=[min(y),max(y)])
        p = p.convert()

        return p
