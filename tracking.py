import json
import logging
import os
import time
from datetime import datetime

import config
import plotter
import util

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

laptime_map = {}
gap_ahead_map = {}
gap_top_map = {}
stint_map = {}
position_map = {}

lap_end_map = {}

lap_number_map = {}
current_positon = {}

results_path = config.live_data_path + "/results"
logs_path = results_path + "/logs"
images_path = results_path + "/images"


def to_json_style(s):
    replaced = s.replace("'", '"') \
        .replace('True', 'true') \
        .replace('False', 'false')
    return replaced


def handle_timing_data(data, time):
    if not isinstance(data, dict):
        return
    for driver, v in data['Lines'].items():
        driver_number = int(driver)
        if 'LastLapTime' in v and 'NumberOfLaps' in v:
            lap_time: str = v["LastLapTime"]["Value"]
            lap_number: int = v["NumberOfLaps"]
            if lap_time != "":
                t = util.time_str_to_seconds(lap_time)
                util.push(driver_number, lap_number, laptime_map, t)
            util.push(driver_number, lap_number, lap_end_map, time)
        if 'Position' in v:
            position_str: str = v["Position"]
            position = int(position_str)
            util.push(driver_number, time, position_map, position)
        if 'GapToLeader' in v:
            if not 'L' in v["GapToLeader"]:
                diff_str: str = v["GapToLeader"].replace("+", "")
                diff = util.time_str_to_seconds(diff_str)
                util.push(driver_number, time, gap_top_map, diff)
        if 'IntervalToPositionAhead' in v:
            if 'Value' in v["IntervalToPositionAhead"]:
                if not 'L' in v["IntervalToPositionAhead"]["Value"]:
                    diff_str: str = v["IntervalToPositionAhead"]["Value"].replace("+", "")
                    diff = util.time_str_to_seconds(diff_str)
                    util.push(driver_number, time, gap_ahead_map, diff)


def handle_timing_app_data(data, time):
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
                t = util.time_str_to_seconds(lap_time)
                util.push(driver_number, lap_number, lap_end_map, t)
                util.push(driver_number, lap_number, lap_end_map, time)
            stint_number = int(stint_no)
            util.push_stint('Compound', driver_number, stint_number, stint, stint_map)
            util.push_stint('New', driver_number, stint_number, stint, stint_map)
            util.push_stint('TotalLaps', driver_number, stint_number, stint, stint_map)
            util.push_stint('StartLaps', driver_number, stint_number, stint, stint_map)


air_temp_map = {}
rainfall_map = {}
track_temp_map = {}
wind_speed_map = {}


def handle_weather(data, time):
    if not isinstance(data, dict):
        return
    if 'AirTemp' in data:
        air_temp: str = data["AirTemp"]
        if air_temp != "":
            air_temp_map[time] = float(air_temp)
    if 'Rainfall' in data:
        rainfall: str = data["Rainfall"]
        if rainfall != "":
            rainfall_map[time] = float(rainfall)
    if 'TrackTemp' in data:
        trackTemp: str = data["TrackTemp"]
        if trackTemp != "":
            track_temp_map[time] = float(trackTemp)
    if 'WindSpeed' in data:
        windSpeed: str = data["WindSpeed"]
        if windSpeed != "":
            wind_speed_map[time] = float(windSpeed)


def handle_session_data(t, data):
    if 'StatusSeries' not in data:
        return
    items = data["StatusSeries"]

    if isinstance(items, list):
        log.warning(f"session data is a list {items}")
        return

    for no, value in items.items():
        message = util.join_with_colon(t, str(no), str(value))
        util.write_to_file_top(f"{logs_path}/session.txt", message)


def handle_session_info_data(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/session_info.txt", message)


def handle_race_control(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/race_control.txt", message)


def handle_track_status(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/track_status.txt", message)


def handle_extrapolated_clock(t, data):
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/extrapolated_clock.txt", message)


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
    if category == "SessionData":
        handle_session_data(msg[2], msg[1])
    if category == "WeatherData":
        handle_weather(msg[1], datetime.fromisoformat(msg[2].replace("Z", "+00:00")))
    if category == "SessionInfo":
        handle_session_info_data(msg[2], msg[1])
    if category == "RaceControlMessages":
        handle_race_control(msg[2], msg[1])
    if category == "TrackStatus":
        handle_track_status(msg[2], msg[1])
    if category == "ExtrapolatedClock":
        handle_extrapolated_clock(msg[2], msg[1])


os.makedirs(images_path, exist_ok=True)
os.makedirs(logs_path + "/positions", exist_ok=True)
os.makedirs(logs_path + "/ahead_diffs", exist_ok=True)
os.makedirs(logs_path + "/fastest_diffs", exist_ok=True)

try:
    os.remove(f"{logs_path}/session.txt")
except FileNotFoundError:
    pass
try:
    os.remove(f"{logs_path}/session_info.txt")
except FileNotFoundError:
    pass
try:
    os.remove(f"{logs_path}/race_control.txt")
except FileNotFoundError:
    pass
try:
    os.remove(f"{logs_path}/track_status.txt")
except FileNotFoundError:
    pass
try:
    os.remove(f"{logs_path}/extrapolated_clock.txt")
except FileNotFoundError:
    pass

file_path = "live/data/source/2025_Monaco_Race.txt"  # 読み込むファイル
start = 0  # 最初に読み込んだ行数
prev_start = -1  # 直前の読み込み行数（初期値は不一致にしておく）

while True:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        new_lines = lines[start:]  # 新しい行だけ取得

        for line in new_lines:
            line = line.strip()
            if line:
                handle(line)

        prev_start, start = start, len(lines)  # 前回のstartを保存し、今回のstartを更新

    # ファイルが更新されていた場合のみplotを実行
    if start != prev_start:
        plotter.plot_tyres(stint_map)
        plotter.plot_with_lap_end(lap_end_map, gap_ahead_map, "gap_ahead", 0, 10)
        plotter.plot_with_lap_end(lap_end_map, gap_top_map, "gap_top", 0, 35)
        plotter.plot_positions(lap_end_map, position_map, "position")
        plotter.plot_laptime(laptime_map, "laptime", 3, 1)
        plotter.plot_laptime_diff(laptime_map, "laptime_diffs", 0.75, 0.75)

        plotter.plot_weather(air_temp_map, 'air_temp')
        plotter.plot_weather(rainfall_map, 'rainfall')
        plotter.plot_weather(track_temp_map, 'track_temp')
        plotter.plot_weather(wind_speed_map, 'wind_speed')
    else:
        log.info("plot is skipped")
    util.write_to_file_top(f"{logs_path}/timestamp.txt", f"{datetime.now()}")
    time.sleep(60)
