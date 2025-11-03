#!/usr/bin/env python3

import os

from flask import Flask, redirect, url_for, request
from flask import render_template

from dotenv import load_dotenv

from SmokerMonitor import SmokerMonitor
from MeaterMonitor import MeaterMonitor
from MQTTPublisher import MQTTPublisher
from HASSTempSender import HASSTempSender

import json

load_dotenv()

class SmokoTime:
    def __init__(self, monitor: SmokerMonitor, meater: MeaterMonitor):
        self.app = Flask('SmokoTime')
        self.app.config.update(TEMPLATES_AUTO_RELOAD=True)
        self.smoker_monitor = monitor
        self.meater_monitor = meater
        self.initialize_routes()

    def initialize_routes(self):
        @self.app.route('/')
        def __index():
            monitoring_state = self.smoker_monitor.monitoring_state
            monitoring_action = 'Start' if monitoring_state == 'Stopped' else 'Stop'
            temp_hist = self.smoker_monitor.temp_history
            temp_data = temp_hist.temp_history
            if len(temp_data) != 0:
                latest_data = temp_data[-1]
            else:
                latest_data = {
                    'temperature': 0,
                    'set_temperature': 0,
                    'delta': 0
                }

            # print(f'self.smoker_monitor.enabled = {self.smoker_monitor.enabled}')
            return render_template(
                'index.html',
                current_temp        = latest_data['temperature'],
                target_temp         = self.smoker_monitor.temp_history.target_temp,
                target_delta        = self.smoker_monitor.temp_history.delta,
                monitoring_interval = self.smoker_monitor.monitoring_interval,
                hass_sensor_name    = self.smoker_monitor.hass_sensor,
                hass_entity_name    = self.smoker_monitor.hass_entity,
                hass_sensor_enabled = "checked" if self.smoker_monitor.hass_sensor_enabled else "",
                heater_state        = self.smoker_monitor.heating_state,
                monitoring_action   = monitoring_action,
                monitoring_state    = monitoring_state,
                element_state       = "On" if self.smoker_monitor.enabled else "Off",
                proportional_gain   = self.smoker_monitor.proportional_gain,
                integral_gain       = self.smoker_monitor.integral_gain,
                integral_windup_guard       = self.smoker_monitor.integral_windup_guard,
                derivative_gain     = self.smoker_monitor.derivative_gain,
                listen_port         = self.port,
                alpha               = self.smoker_monitor.alpha
            )

        @self.app.route('/update_temps', methods=['POST'])
        def __update_temps():
            if request.method == 'POST':
                target_temp = (float(request.form['target_temp']) - 32.0) * 5.0/9.0
                target_delta = (float(request.form['target_delta']) * 5.0/9.0)

                print(f'Setting target_temp to {target_temp} C and target_delta to {target_delta} C')
                temp_history = self.smoker_monitor.temp_history
                temp_history.target_temp = target_temp
                temp_history.delta = target_delta

                interval = int(request.form['interval'])
                print(f'Setting monitoring_interval to {interval}')
                self.smoker_monitor.monitoring_interval = interval
                self.meater_monitor.monitoring_interval = interval

                return redirect(url_for('__index'))

        @self.app.route('/update_advanced', methods=['POST'])
        def __update_advanced():
            if request.method == 'POST':
                hass_sensor_name = request.form['hass_sensor_name']
                hass_entity_name = request.form['hass_entity_name']
                if request.form.get('hass_enable'):
                    self.smoker_monitor.enable_hass_sensor()
                else:
                    self.smoker_monitor.disable_hass_sensor()

                print(f'Setting HASS sensor name to {hass_sensor_name} and HASS switch to {hass_entity_name}')
                self.smoker_monitor.hass_sensor = hass_sensor_name
                self.smoker_monitor.hass_entity = hass_entity_name

                # PID control params
                self.smoker_monitor.proportional_gain = float(request.form['proportional_gain'])
                self.smoker_monitor.integral_gain = float(request.form['integral_gain'])
                self.smoker_monitor.integral_windup_guard = float(request.form['integral_windup_guard'])
                self.smoker_monitor.derivative_gain = float(request.form['derivative_gain'])
                self.smoker_monitor.alpha = float(request.form['alpha'])

                # self.smoker_monitor.mqtt_switch = mqtt_switch_name
                return redirect(url_for('__index'))

        @self.app.route('/toggle_monitoring', methods=['POST'])
        def __toggle_monitoring():
            if request.method == 'POST':
                if request.form['monitoring_action'] == 'Start':
                    self.smoker_monitor.start_temp_monitor()
                    self.meater_monitor.start()
                else:
                    self.smoker_monitor.stop_temp_monitor()
                    self.meater_monitor.stop()
                return redirect(url_for('__index'))

        @self.app.route('/temp_history', methods=['GET'])
        def __get_temp_history():
            """Get all the temperature history"""
            if request.method == 'GET':
                return self.smoker_monitor.temp_history.temp_history

        @self.app.route('/temp_history/since/<index>', methods=['GET'])
        def __get_temp_history_since(index):
            """Get the temperature since the specified index"""
            if request.method == 'GET':
                since = int(index)
                values = self.smoker_monitor.temp_history.temp_history_since(since)
                return values

        @self.app.route('/meater/cooks', methods=['GET'])
        def __get_meater_cooks():
            """Get the cook id -> cook name dictionary"""
            if request.method == 'GET':
                return self.meater_monitor.history.cooks

        @self.app.route('/meater/history', methods=['GET'])
        def __get_meater_history():
            """Get all the meater history"""
            if request.method == 'GET':
                return self.meater_monitor.history.history

        @self.app.route('/meater/history/since/<index>', methods=['GET'])
        def __get_meater_history_since(index):
            """Get the meater since the specified index"""
            if request.method == 'GET':
                since = int(index)
                print(f'Index = {index} :: Since = {since}')
                values = self.meater_monitor.history.history_since(since)
                return values

        @self.app.route('/state', methods=['GET'])
        def __get_state():
            """Get all the temperature history"""
            if request.method == 'GET':
                return {
                    'state': self.smoker_monitor.monitoring_state,
                    'action': self.smoker_monitor.action,
                    'heater_state': self.smoker_monitor.heating_state
                }

        @self.app.route('/toggle_element', methods=['POST'])
        def __toggle_element():
            """Enable the heating element"""
            # print(json.dumps(request.form));
            if request.form.get('element_action'):
                self.smoker_monitor.enable()
            else:
                self.smoker_monitor.disable()
            return redirect(url_for('__index'))


        @self.app.route('/element', methods=['GET'])
        def __get_element():
            """Get the heating element status"""
            if self.smoker_monitor.enabled:
                return "enabled"
            else:
                return "disabled"

        @self.app.route('/thermocouple_details', methods=['GET'])
        def __get_thermocouple_details():
            """Get the thermocouple details from the monitor"""
            if request.method == 'GET':
                return self.smoker_monitor.thermocouple_details()


    def run(self, **kwargs):
        self.port = kwargs.get("port", -1)
        if self.port == -1:
            print("Unable to get port from args");
            return;
        self.app.run(**kwargs)

    def index(self):
        temp_data = self.smoker_monitor.temp_history.temp_history
        if len(temp_data) != 0:
            latest_data = temp_data[-1]
        else:
            latest_data = {
                'temperature': 0,
                'set_temperature': 0,
                'delta': 0
            }
        return f'<p>Hello</p><p>Last temp was {latest_data["temperature"]}</p>'

mqtt_server = os.getenv('MQTT_SERVER')
mqtt_user = os.getenv('MQTT_USER')
mqtt_pass = os.getenv('MQTT_PASS')
hass_server = os.getenv('HASS_SERVER')
hass_token = os.getenv('HASS_TOKEN')
listen_port = os.getenv('LISTEN_PORT')
listen_host = os.getenv('LISTEN_HOST')

# Related to Meater
meater_user = os.getenv('MEATER_USER')
meater_pass = os.getenv('MEATER_PASS')

# sm = SmokerMonitor(mqtt_server, hass_server, hass_token, mqtt_user, mqtt_pass, target_temp = 51.66, target_delta = 1.388)
sm = SmokerMonitor(hass_server, hass_token, target_temp = 128.055555, target_delta = 5.55555555)
# sm.start_temp_monitor()
mm = MeaterMonitor(meater_user, meater_pass)
sw = SmokoTime(sm, mm)

sw.run(host=listen_host, port=listen_port)

# app = Flask(__name__)

# @app.route('/')
# def hello_world():
#     return "<p>Hello</p>"
