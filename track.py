import json
import logging
import os
import time

import fastf1
from fastf1.core import DataNotLoadedError
from fastf1.livetiming.data import LiveTimingData

from visualizations import race, weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

fastf1.Cache.enable_cache('./cache', force_renew=True)
with open('./config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

results_path = "./live/data/results"
logs_path = results_path + "/logs"
images_path = results_path + "/images"
os.makedirs(logs_path, exist_ok=True)
os.makedirs(images_path, exist_ok=True)

while True:
    try:
        livedata = LiveTimingData('./live/data/source/'+config['FileName'], _files_read=True)
        livedata.load()
        session = fastf1.get_session(config['Year'], config['Round'], 'Race')
        session.load(livedata=livedata)
        race.execute(session, log, "./live/data/results/images", "./live/data/results/logs")
        weather.execute(session, log, "./live/data/results/images")
    except DataNotLoadedError as e:
        log.warning(e)
        time.sleep(30)
        continue
    time.sleep(60)
