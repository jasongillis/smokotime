from flask import Flask, redirect, url_for, request
from flask import render_template
from SmokerMonitor import SmokerMonitor
from MQTTPublisher import MQTTPublisher
from HASSTempSender import HASSTempSender

class SmokerWeb:
    def __init__(self, monitor: SmokerMonitor):
        self.app = Flask('SmokerWeb')
        self.app.config.update(TEMPLATES_AUTO_RELOAD=True)
        self.smoker_monitor = monitor
        self.initialize_routes()

    def initialize_routes(self):
        @self.app.route('/')
        def __index():
            monitoring_state = self.smoker_monitor.monitoring_state
            monitoring_action = 'Start' if monitoring_state == 'Stopped' else 'Stop'
            return render_template(
                'index.html',
                current_temp=self.smoker_monitor.latest_temp,
                target_temp=self.smoker_monitor.target_temp,
                target_delta=self.smoker_monitor.target_delta,
                chart_data=self.smoker_monitor.temp_history,
                hass_sensor_name=self.smoker_monitor.hass_sensor,
                mqtt_switch_name=self.smoker_monitor.mqtt_switch,
                monitoring_action=monitoring_action,
                monitoring_state=monitoring_state
            )

        @self.app.route('/update_temps', methods=['POST'])
        def __update_temps():
            if request.method == 'POST':
                target_temp = (float(request.form['target_temp']) - 32.0) * 5.0/9.0
                target_delta = (float(request.form['target_delta']) * 5.0/9.0)
                print(f'Setting target_temp to {target_temp} C and target_delta to {target_delta} C')
                self.smoker_monitor.target_temp = target_temp
                self.smoker_monitor.target_delta = target_delta
                return redirect(url_for('__index'))

        @self.app.route('/update_advanced', methods=['POST'])
        def __update_advanced():
            if request.method == 'POST':
                hass_sensor_name = request.form['hass_sensor_name']
                mqtt_switch_name = request.form['mqtt_switch_name']
                print(f'Setting HASS sensor name to {hass_sensor_name} and MQTT switch to {mqtt_switch_name}')
                self.smoker_monitor.hass_sensor = hass_sensor_name
                self.smoker_monitor.mqtt_switch = mqtt_switch_name
                return redirect(url_for('__index'))

        @self.app.route('/toggle_monitoring', methods=['POST'])
        def __toggle_monitoring():
            if request.method == 'POST':
                if request.form['monitoring_action'] == 'Start':
                    self.smoker_monitor.start_temp_monitor()
                else:
                    self.smoker_monitor.stop_temp_monitor()
                return redirect(url_for('__index'))

        @self.app.route('/temp_history', methods=['GET'])
        def __get_temp_history():
            if request.method == 'GET':
                return self.smoker_monitor.temp_history

    def run(self, **kwargs):
        self.app.run(**kwargs)

    def index(self):
        return f'<p>Hello</p><p>Last temp was {self.smoker_monitor.get_latest_temp()}</p>'

mqtt_server = 'server.house'
mqtt_user = 'mqttdev'
mqtt_pass = '***REMOVED***'
hass_server = 'server.house'
hass_token = "***REMOVED***"
sm = SmokerMonitor(mqtt_server, hass_server, hass_token, mqtt_user, mqtt_pass, target_temp = 51.66, target_delta = 1.388)
# sm.start_temp_monitor()

sw = SmokerWeb(sm)

sw.run(host="0.0.0.0")

# app = Flask(__name__)

# @app.route('/')
# def hello_world():
#     return "<p>Hello</p>"
