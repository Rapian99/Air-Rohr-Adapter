from loguru import logger
import sys
from flask import Flask, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app, Gauge, Counter, Info
from waitress import serve
import threading
import yaml
from os import path


APPLICATION_NAME = "Air-Rohr-Adapter"
port = 5000
FORMAT = "{time} | {level} | {file}:{line} | {message}"
INFO = Info('my_build_version', 'Description of info')
INFO.info({'version': 'v0.1.0', 'buildhost': 'PRD', 'builddate': '2025-03-03'})
C = Counter('requests_total', 'HTTP Requests', ['app', 'method', 'endpoint'])
GAUGE_LABELS = ['app', 'Sensor', 'id', 'interval', 'software_version']
SENSOR = Gauge('sensor_samples', 'Sensor samples and info', GAUGE_LABELS)
SIGNAL = Gauge('sensor_signal', 'Sensor signal and info', GAUGE_LABELS)
MIN = Gauge('sensor_min_micro', 'Sensor min and info', GAUGE_LABELS)
MAX = Gauge('sensor_max_micro', 'Sensor max and info', GAUGE_LABELS)
PM10 = Gauge('sensor_pm10', 'PM10 value', ['app', 'Sensor', 'id'])
PM25 = Gauge('sensor_pm25', 'PM25 value', ['app', 'Sensor', 'id'])
TEMP = Gauge('sensor_temp', 'Temperature value', ['app', 'Sensor', 'id'])
HUM = Gauge('sensor_humidity', 'Humidity value', ['app', 'Sensor', 'id'])
PRESS = Gauge('sensor_pressure', 'Pressure value', ['app', 'Sensor', 'id'])


logger.remove()
logger.add(sys.stdout, level="INFO", format="{time}  {message} ")

logger.info("##############################################################")
logger.info("|                                                            |")
logger.info("|                Starting air-rohr-adapter                   |")
logger.info("|                                                            |")
logger.info("##############################################################")


@logger.catch
def configuration_loader():
    """Function responsible for loading configuration file"""
    message = "Error while loading configuration!"
    try:
        if path.isfile("./configuration.yaml"):
            with open("./configuration.yaml", "r") as config:
                logger.info("Configuration loaded correctly")
                return yaml.safe_load(config)
        else:
            raise FileNotFoundError("Configuration file not found")
    except yaml.YAMLError as error:
        logger.critical(f"{message} - App killed! - {format(error)}")
        sys.exit(message)
    except BaseException as error:
        logger.critical(f"{message} - App killed! - {format(error)}")
        sys.exit(message)


app = Flask(__name__)
requests = []


@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.url}")
    logger.debug(f"Headers: {request.headers}")
    logger.debug(f"Body: {request.get_data()}")


@app.route("/ara/v1/push", methods=["POST"])
def api():
    try:
        logger.info(f"API request received: {request}")
        headers = dict(request.headers)
        data = request.get_json(silent=True)
        if data is None:
            logger.error("No data received in the request")
            return '', 400
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data received: {data}")
        req = [headers, data]
        requests.append(req)
        logger.debug(f"Request added to list: {requests}")
        C.labels(
            app=APPLICATION_NAME, method='post', endpoint='/ara/v1/push'
            ).inc()
        return '', 200
    except BaseException as api_error:
        logger.error(f"Error while processing API request: {api_error}")
        return '', 500


@logger.catch
def metrics(sensor, espid, software_version, data):
    try:
        logger.debug("Metrics request received")
        for x in data:
            if x["value_type"] == "SDS_P1":
                PM10.labels(
                    APPLICATION_NAME, sensor, espid
                    ).set(float(x["value"]))
            elif x["value_type"] == "SDS_P2":
                PM25.labels(
                    APPLICATION_NAME, sensor, espid
                    ).set(float(x["value"]))
            elif x["value_type"] == "BME280_temperature":
                TEMP.labels(
                    APPLICATION_NAME, sensor, espid
                    ).set(float(x["value"]))
            elif x["value_type"] == "BME280_humidity":
                HUM.labels(
                    APPLICATION_NAME, sensor, espid
                    ).set(float(x["value"]))
            elif x["value_type"] == "BME280_pressure":
                PRESS.labels(
                    APPLICATION_NAME, sensor, espid
                    ).set(float(x["value"]))
        samples = data[5]["value"]
        minmicro = data[6]["value"]
        maxmicro = data[7]["value"]
        interval = data[8]["value"]
        signal = data[9]["value"]

        labels = {
            'app': APPLICATION_NAME,
            'Sensor': sensor,
            'id': espid,
            'interval': interval,
            'software_version': software_version
        }

        SENSOR.labels(**labels).set(float(samples))
        SIGNAL.labels(**labels).set(float(signal))
        MIN.labels(**labels).set(float(minmicro))
        MAX.labels(**labels).set(float(maxmicro))
        logger.info("Metrics processed successfully")
    except BaseException as metrics_error:
        logger.error(
            f"Error while processing metrics request: {metrics_error}"
            )


@logger.catch
def main():
    config = configuration_loader()
    if "port" in config:
        port=config["port"]
    if "logs_level" in config:
        log_level=config["logs_level"]
    else:
        log_level="INFO"
    logger.remove()
    logger.add(sys.stdout, level=log_level, format=FORMAT)
    logger.info(
        f"!!! Air-rohr-adapter started successfully on port {port} !!!"
        )

    stop_event = threading.Event()

    def process_with_event():
        try:
            while not stop_event.is_set():
                if len(requests) > 0:
                    req = requests.pop(0)
                    headers = req[0]
                    data = req[1]
                    logger.info(f"Processing request: {headers}")
                    metrics(
                        headers["X-Sensor"],
                        data["esp8266id"],
                        data["software_version"],
                        data["sensordatavalues"]
                        )
                else:
                    logger.trace("No requests to process")
                    stop_event.wait(1)
        except BaseException as process_error:
            logger.error(f"Error while processing requests: {process_error}")

    threading.Thread(target=process_with_event, daemon=True).start()

    try:
        app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
            '/metrics': make_wsgi_app()
        })
        serve(app, host='0.0.0.0', port=port)
    except Exception as mainexception:
        logger.error(f"Failed to start the application: {mainexception}")
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
