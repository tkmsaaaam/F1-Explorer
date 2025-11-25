import json
import logging
import os
import time
from datetime import datetime

import util
from backup import plotter
from backup.domain.Stint import Stint
from backup.domain.lap import Lap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

laptime_map: dict[int, dict[int, Lap]] = {}
stints_map: dict[int, dict[int, Stint]] = {}

results_path = "../live/data/results"
logs_path = results_path + "/logs"
images_path = results_path + "/images"


def str_to_seconds(param: str) -> float:
    if param == "":
        return 0
    parts = param.split(":")

    if len(parts) == 1:
        # "SSS.sss"
        return float(parts[0])
    elif len(parts) == 2:
        # "MM:SS.sss"
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 3:
        # "HH:MM:SS.sss"
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        raise ValueError(f"Unsupported time format: {param}")


def to_json_style(s: str) -> str:
    replaced = s.replace("'", '"') \
        .replace('True', 'true') \
        .replace('False', 'false')
    return replaced


def handle_timing_data(data, t: datetime):
    if not isinstance(data, dict):
        return
    for driver, v in data['Lines'].items():
        driver_number = int(driver)
        if 'LastLapTime' in v and 'NumberOfLaps' in v:
            lap_time: str = v["LastLapTime"]["Value"]
            lap_number: int = v["NumberOfLaps"]
            if lap_time != "":
                if driver_number not in laptime_map:
                    laptime_map[driver_number] = {}
                lap = Lap()
                lap.set_time(str_to_seconds(lap_time))
                lap.set_at(t)
                laptime_map[driver_number][lap_number] = lap
        if 'Position' in v:
            position_str: str = v["Position"]
            position = int(position_str)
            if driver_number not in laptime_map:
                lap = Lap()
                lap.set_position(position)
                laptime_map[driver_number] = {0: lap}
            if len(laptime_map.get(driver_number).keys()) > 0:
                laptime_map.get(driver_number).get(max(laptime_map.get(driver_number).keys())).set_position(position)
        if 'GapToLeader' in v:
            if not 'L' in v["GapToLeader"]:
                diff_str: str = v["GapToLeader"].replace("+", "")
                diff = str_to_seconds(diff_str)
                if driver_number not in laptime_map:
                    lap = Lap()
                    lap.set_gap_to_top(diff)
                    laptime_map[driver_number] = {0: lap}
                if len(laptime_map.get(driver_number).keys()) > 0:
                    laptime_map.get(driver_number).get(max(laptime_map.get(driver_number).keys())).set_gap_to_top(
                        diff)
        if 'IntervalToPositionAhead' in v:
            if 'Value' in v["IntervalToPositionAhead"]:
                if not 'L' in v["IntervalToPositionAhead"]["Value"]:
                    diff_str: str = v["IntervalToPositionAhead"]["Value"].replace("+", "")
                    diff = str_to_seconds(diff_str)
                    if driver_number not in laptime_map:
                        lap = Lap()
                        lap.set_gap_to_ahead(diff)
                        laptime_map[driver_number] = {0: lap}
                    if len(laptime_map.get(driver_number).keys()) > 0:
                        laptime_map.get(driver_number).get(max(laptime_map.get(driver_number).keys())).set_gap_to_ahead(
                            diff)


def handle_timing_app_data(data, handled_time: datetime):
    if not isinstance(data, dict):
        return
    for driver, v in data['Lines'].items():
        if not 'Stints' in v:
            continue
        stints = v['Stints']
        if not isinstance(stints, dict):
            continue
        driver_number = int(driver)
        for stint_no, stint in stints.items():
            if 'LapTime' in stint and 'LapNumber' in stint:
                lap_time = stint["LapTime"]
                lap_number = stint["LapNumber"]
                if driver_number not in laptime_map:
                    laptime_map[driver_number] = {}
                if lap_number not in laptime_map[driver_number]:
                    lap = Lap()
                    lap.set_at(handled_time)
                    lap.set_time(str_to_seconds(lap_time))
                    laptime_map[driver_number][lap_number] = lap
            if driver_number not in stints_map:
                stints_map[driver_number] = {}
            s = stints_map[driver_number]
            stint_number = int(stint_no)
            if stint_number not in s:
                s[stint_number] = Stint()
            if 'Compound' in stint:
                s[stint_number].set_compound(stint['Compound'])
            if 'New' in stint:
                s[stint_number].set_is_new(stint['New'])
            if 'TotalLaps' in stint:
                s[stint_number].set_total_laps(stint['TotalLaps'])
            if 'StartLaps' in stint:
                s[stint_number].set_start_laps(stint['StartLaps'])


air_temp_map = {}
rainfall_map = {}
track_temp_map = {}
wind_speed_map = {}


def handle_weather(data, t: datetime):
    if not isinstance(data, dict):
        return
    if 'AirTemp' in data:
        air_temp: str = data["AirTemp"]
        if air_temp != "":
            air_temp_map[t] = float(air_temp)
    if 'Rainfall' in data:
        rainfall: str = data["Rainfall"]
        if rainfall != "":
            rainfall_map[t] = float(rainfall)
    if 'TrackTemp' in data:
        track_temp: str = data["TrackTemp"]
        if track_temp != "":
            track_temp_map[t] = float(track_temp)
    if 'WindSpeed' in data:
        wind_speed: str = data["WindSpeed"]
        if wind_speed != "":
            wind_speed_map[t] = float(wind_speed)


def handle_race_control(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/race_control.txt", message)


def handle_track_status(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/track_status.txt", message)


def handle(message):
    json_str = to_json_style(message)
    try:
        msg = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        log.warning("Json parse error %s", message)
        return
    category = msg[0]
    if category == "TimingAppData":
        handle_timing_app_data(msg[1], datetime.fromisoformat(msg[2].replace("Z", "+00:00")))
    if category == "TimingData":
        handle_timing_data(msg[1], datetime.fromisoformat(msg[2].replace("Z", "+00:00")))
    if category == "WeatherData":
        handle_weather(msg[1], datetime.fromisoformat(msg[2].replace("Z", "+00:00")))
    if category == "RaceControlMessages":
        handle_race_control(msg[2], msg[1])
    if category == "TrackStatus":
        handle_track_status(msg[2], msg[1])


os.makedirs(images_path, exist_ok=True)

try:
    os.remove(f"{logs_path}/race_control.txt")
except FileNotFoundError:
    pass
try:
    os.remove(f"{logs_path}/track_status.txt")
except FileNotFoundError:
    pass

with open('../config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

start = 0  # 最初に読み込んだ行数
prev_start = -1  # 直前の読み込み行数（初期値は不一致にしておく）

while True:
    with open('../live/data/source/' + config['FileName'], "r", encoding="utf-8") as f:
        lines = f.readlines()
        new_lines = lines[start:]  # 新しい行だけ取得

        for line in new_lines:
            line = line.strip()
            if line:
                handle(line)

        prev_start, start = start, len(lines)  # 前回のstartを保存し、今回のstartを更新

    # ファイルが更新されていた場合のみplotを実行
    if start != prev_start:
        plotter.plot_tyres(stints_map)
        plotter.plot_gap_to_ahead(laptime_map, "gap_ahead", 8)
        plotter.plot_gap_to_top(laptime_map, "gap_top", 35)
        plotter.plot_positions(laptime_map, "position")
        plotter.plot_laptime(laptime_map, "laptime", 7)
        plotter.plot_laptime_diff(laptime_map, "laptime_diffs", 0.75, 0.75)

        plotter.plot_weather(air_temp_map, 'air_temp')
        plotter.plot_weather(rainfall_map, 'rainfall')
        plotter.plot_weather(track_temp_map, 'track_temp')
        plotter.plot_weather(wind_speed_map, 'wind_speed')
    else:
        log.info("plot is skipped")
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", f"{datetime.now()}")
    time.sleep(60)
