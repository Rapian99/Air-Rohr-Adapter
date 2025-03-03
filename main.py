from loguru import logger
import sys
from flask import Flask, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app, Gauge, Counter, Info
import threading

APPLICATION_NAME = "Air-Rohr-Adapter"
PORT = 5000
I = Info('my_build_version', 'Description of info')
I.info({'version': 'v0.0.1', 'buildhost': 'test', 'builddate': '2025-03-03'})
C = Counter('requests_total', 'HTTP Requests', ['app', 'method', 'endpoint'])
PM10 = Gauge('sensor_pm10', 'PM10 value', ['app', 'Sensor', 'id'])
PM25 = Gauge('sensor_pm25', 'PM25 value', ['app', 'Sensor', 'id'])
TEMP = Gauge('sensor_temperature', 'Temperature value', ['app', 'Sensor', 'id'])
HUM = Gauge('sensor_humidity', 'Humidity value', ['app', 'Sensor', 'id'])
PRESS = Gauge('sensor_pressure', 'Pressure value', ['app', 'Sensor', 'id'])


logger.remove()
logger.add(sys.stdout, level="INFO", format="{time}  {message} ")

logger.info("########################################################################################")
logger.info("|                                                                                      |")
logger.info("|                              Starting air-rohr-adapter                               |")
logger.info("|                                                                                      |")
logger.info("########################################################################################")

logger.remove()
logger.add(sys.stdout, level="DEBUG", format="{time} | {level} | {file} | {line} | {exception}| {message} ")


app = Flask(__name__)
requests = []


@app.route("/ara/v1/push", methods=["POST"])
def api():
    try:
        logger.debug(f"API request received: {request}")
        headers = dict(request.headers)
        data = request.get_json(silent=True)
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data received: {data}")
        req = [headers, data]
        requests.append(req)
        logger.debug(f"Request added to list: {requests}")
        C.labels(app= APPLICATION_NAME, method='get', endpoint='/ara/v1/push').inc()
        return '', 200
    except BaseException as api_error:
        logger.error(f"Error while processing API request: {api_error}")
        return '', 500


@logger.catch
def metrics(sensor, espid, data):
    try:
        logger.debug("Metrics request received")
        print(type(data))
        for x in data:
            print(type(x))
            if x["value_type"] == "SDS_P1":
                PM10.labels(app=APPLICATION_NAME, Sensor=sensor, id=espid).set(float(x["value"]))
            elif x["value_type"] == "SDS_P2":
                PM25.labels(app=APPLICATION_NAME, Sensor=sensor, id=espid).set(float(x["value"]))
            elif x["value_type"] == "BME280_temperature":
                TEMP.labels(app=APPLICATION_NAME, Sensor=sensor, id=espid).set(float(x["value"]))
            elif x["value_type"] == "BME280_humidity":
                HUM.labels(app=APPLICATION_NAME, Sensor=sensor, id=espid).set(float(x["value"]))
            elif x["value_type"] == "BME280_pressure":
                PRESS.labels(app=APPLICATION_NAME, Sensor=sensor, id=espid).set(float(x["value"]))
        logger.debug("Metrics processed successfully")
    except BaseException as metrics_error:
        logger.error(f"Error while processing metrics request: {metrics_error}")


@logger.catch
def process():
    try:
        while True:
            if len(requests) > 0:
                req = requests.pop(0)
                headers = req[0]
                data = req[1]
                print(f"{type(data)}:{data}")
                dataval= data["sensordatavalues"]
                print(f"{type(dataval)}:{dataval}")
                logger.info(f"Processing request: {headers}")
                metrics(headers["X-Sensor"], data["esp8266id"], dataval)
            else:
                logger.trace("No requests to process")
                continue
    except BaseException as process_error:
        logger.error(f"Error while processing requests: {process_error}")

# @C.labels(app= APPLICATION_NAME, method='get', endpoint='/metrics').inc()
def run_metrics():
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })


@logger.catch
def main():
    logger.info(f"!!! Air-rohr-adapter started successfully on port {PORT} !!!")
    threading.Thread(target=process, daemon=True).start()
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()