import json
import logging

from fastf1.livetiming.client import SignalRClient

log = logging.getLogger()
log.setLevel(logging.INFO)

with open('../config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

client = SignalRClient(filename=config['FilePath'], debug=False, timeout=1800, filemode='a')

client.start()
