import logging
from fastf1.livetiming.client import SignalRClient

log = logging.getLogger()
log.setLevel(logging.INFO)

client = SignalRClient(filename="./live/data/source/2025_Monaco_Race.txt", debug=False, timeout=1800, filemode='a')

client.start()
