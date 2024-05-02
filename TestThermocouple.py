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

print('Create SPI')
spi = board.SPI()
print('Create CS')
cs = digitalio.DigitalInOut(board.D5)
print('Set direction')
cs.direction = digitalio.Direction.OUTPUT

print('Create MAX31856')
thermoc = adafruit_max31856.MAX31856(spi, cs, thermocouple_type=ThermocoupleType.K)
print('Set averaging to 4')
thermoc.averaging = 4

print('Getting temperature')
temp = thermoc.temperature
print(f'Temp = {temp}')
