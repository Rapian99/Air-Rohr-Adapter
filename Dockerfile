FROM python:3.13.2-alpine3.21
WORKDIR /air-rohr-adapter
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY main.py main.py
COPY configuration.yaml configuration.yaml
CMD python main.py