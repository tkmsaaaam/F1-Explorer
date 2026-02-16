import datetime
import json
import logging
import os
import time
from pathlib import Path

import setup
import util
from tracker import plotter
from tracker.domain.lap import Lap
from tracker.domain.stint import Stint
from tracker.domain.weather import Weather


class Config:
    """Configuration holder for race tracking logging and output paths.

    Attributes:
        __log: Logger instance for logging messages.
        __logs_path: Path to the directory where logs will be written.
    """

    def __init__(self, log: logging.Logger, logs_path: str):
        """Initialize Config with logger and logs path.

        Args:
            log: Logger instance for logging messages.
            logs_path: Path to the directory where logs will be written.
        """
        self.__log = log
        self.__logs_path = logs_path

    def get_log(self):
        """Get the logger instance.

        Returns:
            The logger instance.
        """
        return self.__log

    def get_logs_path(self):
        """Get the logs directory path.

        Returns:
            The path to the directory where logs are written.
        """
        return self.__logs_path


class Race:
    """Main handler for race timing, stint, and weather data.

    Maintains maps of lap times, stints, and weather information keyed by driver number
    and timestamp. Processes incoming race data from live feed and updates internal state.

    Attributes:
        __laptime_map: Map of driver number -> lap number -> Lap object.
        __stints_map: Map of driver number -> stint number -> Stint object.
        __weather_map: Map of timestamp -> Weather object.
        __config: Configuration object for logging and output paths.
    """

    def __init__(self, config: Config):
        """Initialize Race tracker with configuration.

        Args:
            config: Configuration object containing logger and paths.
        """
        self.__laptime_map: dict[int, dict[int, Lap]] = {}
        self.__stints_map: dict[int, dict[int, Stint]] = {}
        self.__weather_map: dict[datetime.datetime, Weather] = {}
        self.__config = config

    def get_laptime_map(self):
        """Get the lap times map.

        Returns:
            Map of driver number -> lap number -> Lap object.
        """
        return self.__laptime_map

    def get_stints_map(self):
        """Get the stints map.

        Returns:
            Map of driver number -> stint number -> Stint object.
        """
        return self.__stints_map

    def get_weather_map(self):
        """Get the weather data map.

        Returns:
            Map of timestamp -> Weather object.
        """
        return self.__weather_map

    def get_config(self):
        """Get the configuration object.

        Returns:
            The Configuration object.
        """
        return self.__config

    def get_max_lap(self, driver_number: int) -> Lap:
        """Get the most recent lap for a driver.

        Args:
            driver_number: The driver's car number.

        Returns:
            The Lap object with the highest lap number for the driver.
        """
        driver_laps = self.__laptime_map[driver_number]
        return driver_laps.get(max(driver_laps.keys()))

    def _ensure_driver_laps(self, driver_number: int) -> dict:
        """Ensure driver exists in laptime map, creating if necessary.

        Args:
            driver_number: The driver's car number.

        Returns:
            The lap times dictionary for the driver.
        """
        if driver_number not in self.__laptime_map:
            self.__laptime_map[driver_number] = {}
        return self.__laptime_map[driver_number]

    def _ensure_driver_stints(self, driver_number: int) -> dict:
        """Ensure driver exists in stints map, creating if necessary.

        Args:
            driver_number: The driver's car number.

        Returns:
            The stints dictionary for the driver.
        """
        if driver_number not in self.__stints_map:
            self.__stints_map[driver_number] = {}
        return self.__stints_map[driver_number]

    def _ensure_weather(self, t: datetime.datetime) -> Weather:
        """Ensure weather entry exists for timestamp, creating if necessary.

        Args:
            t: The timestamp for the weather data.

        Returns:
            The Weather object for the given timestamp.
        """
        if t not in self.__weather_map:
            self.__weather_map[t] = Weather()
        return self.__weather_map[t]

    def handle_timing_data(self, data):
        """Process timing data: lap times, positions, and gaps.

        Args:
            data: Dictionary containing 'Lines' key with driver-keyed timing information.
                 Fields processed: LastLapTime, Position, GapToLeader, IntervalToPositionAhead.
        """
        if not isinstance(data, dict):
            return
        for driver, v in data.get('Lines', {}).items():
            driver_number = int(driver)
            driver_laps = self._ensure_driver_laps(driver_number)

            # Last lap time
            if 'LastLapTime' in v and 'NumberOfLaps' in v:
                lap_time: str = v["LastLapTime"]["Value"]
                if lap_time:
                    lap = Lap(str_to_seconds(lap_time))
                    if len(driver_laps) > 0:
                        lap.set_position(self.get_max_lap(driver_number).get_position())
                    lap_number = v["NumberOfLaps"]
                    driver_laps[lap_number] = lap

            # Position
            if 'Position' in v:
                position = int(v["Position"])
                if len(driver_laps) == 0:
                    driver_laps[0] = Lap()
                self.get_max_lap(driver_number).set_position(position)

            # Gap to leader
            if 'GapToLeader' in v:
                gap = v["GapToLeader"]
                if 'L' not in gap:
                    if len(driver_laps) == 0:
                        driver_laps[0] = Lap()
                    self.get_max_lap(driver_number).set_gap_to_top(str_to_seconds(gap.replace("+", "")))

            # Interval to position ahead
            if 'IntervalToPositionAhead' in v:
                iva = v["IntervalToPositionAhead"].get("Value") if isinstance(v["IntervalToPositionAhead"],
                                                                              dict) else None
                if iva and 'L' not in iva:
                    if len(driver_laps) == 0:
                        driver_laps[0] = Lap()
                    self.get_max_lap(driver_number).set_gap_to_top(str_to_seconds(iva.replace("+", "")))

    def handle_timing_app_data(self, data):
        """Process timing app data: stint and compound information.

        Args:
            data: Dictionary containing 'Lines' key with driver-keyed stint information.
                 Stints can be dict or list format; processes Compound, New, TotalLaps, StartLaps.
        """
        if not isinstance(data, dict):
            return
        for driver, v in data.get('Lines', {}).items():
            if 'Stints' not in v:
                continue
            stints = v['Stints']
            driver_number = int(driver)
            driver_laps = self._ensure_driver_laps(driver_number)
            s = self._ensure_driver_stints(driver_number)

            # stints as dict
            if isinstance(stints, dict):
                for stint_no, stint in stints.items():
                    # lap info
                    if 'LapTime' in stint and 'LapNumber' in stint:
                        lap_number = stint["LapNumber"]
                        if lap_number not in driver_laps:
                            lap = Lap(str_to_seconds(stint["LapTime"]))
                            if len(driver_laps) > 0:
                                lap.set_position(self.get_max_lap(driver_number).get_position())
                            driver_laps[lap_number] = lap

                    # stint meta
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

            # stints as list (take first)
            elif isinstance(stints, list) and len(stints) > 0:
                stint_number = max(s.keys()) + 1 if len(s) > 0 else 0
                stint = stints[0]
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

    def handle_weather(self, data, t: datetime.datetime):
        """Process weather data at a given timestamp.

        Args:
            data: Dictionary with weather fields: AirTemp, Rainfall, TrackTemp, WindSpeed.
            t: Timestamp for the weather data.
        """
        if not isinstance(data, dict):
            return
        weather = self._ensure_weather(t)
        if 'AirTemp' in data:
            air_temp: str = data["AirTemp"]
            if air_temp:
                weather.set_air_temp(float(air_temp))
        if 'Rainfall' in data:
            rainfall: str = data["Rainfall"]
            if rainfall:
                weather.set_rain_fall(float(rainfall))
        if 'TrackTemp' in data:
            track_temp: str = data["TrackTemp"]
            if track_temp:
                weather.set_track_temp(float(track_temp))
        if 'WindSpeed' in data:
            wind_speed: str = data["WindSpeed"]
            if wind_speed:
                weather.set_wind_speed(float(wind_speed))

    def handle(self, message):
        """Route incoming message to appropriate handler based on message type.

        Args:
            message: String message to parse as JSON and route to handlers.
                    Expected format: [category, data, timestamp, ...]
                    Categories: TimingAppData, TimingData, WeatherData, RaceControlMessages, TrackStatus.
        """
        json_str = to_json_style(message)
        try:
            msg = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            self.get_config().get_log().warning("Json parse error %s", message)
            return
        category = msg[0]
        if category == "TimingAppData":
            self.handle_timing_app_data(msg[1])
        if category == "TimingData":
            self.handle_timing_data(msg[1])
        if category == "WeatherData":
            self.handle_weather(msg[1], datetime.datetime.fromisoformat(msg[2].replace("Z", "+00:00")))
        if category == "RaceControlMessages":
            handle_race_control(msg[2], msg[1], self.get_config().get_logs_path())
        if category == "TrackStatus":
            handle_track_status(msg[2], msg[1], self.get_config().get_logs_path())


def str_to_seconds(param: str) -> float:
    """Convert time string to seconds.

    Handles formats: "SSS.sss", "MM:SS.sss", "HH:MM:SS.sss".

    Args:
        param: Time string in colon-separated format.

    Returns:
        Time in seconds as a float.

    Raises:
        ValueError: If time format is not recognized.
    """
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
    """Normalize Python string representation to JSON-compatible format.

    Converts single quotes to double quotes and Python booleans (True/False) to JSON format (true/false).

    Args:
        s: String with Python-style syntax.

    Returns:
        String normalized to JSON-compatible syntax.
    """
    # normalize to JSON-friendly style: single->double quotes and lowercase booleans
    return s.replace("'", '"').replace('True', 'true').replace('False', 'false')


def handle_race_control(t, data, logs_path: str):
    """Log race control messages to file.

    Args:
        t: Timestamp of the race control message.
        data: Race control message content.
        logs_path: Directory path for writing logs.
    """
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/race_control.txt", message)


def handle_track_status(t, data, logs_path: str):
    """Log track status messages to file.

    Args:
        t: Timestamp of the track status message.
        data: Track status message content.
        logs_path: Directory path for writing logs.
    """
    message = util.join_with_colon(t, str(data))
    util.write_to_file_top(f"{logs_path}/track_status.txt", message)


def __main():
    """Main entry point for live race tracking.

    Reads configuration, monitors source data file for new lines, processes race data,
    generates plots, and continuously loops with 60-second polling intervals.

    Expected config keys:
        FileName: Path to source data file (can be relative, absolute, or include path components).

    Output:
        - Log files: logs/race_control.txt, logs/track_status.txt, logs/timestamp.txt
        - Plot files: images/ directory with lap time, position, gap, tyres, and weather plots.
    """
    log = setup.log()

    results_path = Path(__file__).resolve().parents[1] / 'live' / 'data' / 'results'
    logs_path = results_path / 'logs'
    images_path = results_path / 'images'
    images_path.mkdir(parents=True, exist_ok=True)

    try:
        os.remove(f"{logs_path}/race_control.txt")
    except FileNotFoundError:
        pass
    try:
        os.remove(f"{logs_path}/track_status.txt")
    except FileNotFoundError:
        pass

    cfg_path = Path(__file__).resolve().parents[1] / 'config.json'
    with cfg_path.open('r', encoding='utf-8') as file:
        config = json.load(file)

    race = Race(Config(log, str(logs_path)))

    start = 0  # 最初に読み込んだ行数
    prev_start = -1  # 直前の読み込み行数（初期値は不一致にしておく）

    # determine source file path: if FileName already contains live/data/source or is absolute, use as-is
    fname = config.get('FileName', '')
    if os.path.isabs(fname) or fname.startswith('live/') or 'live/data/source' in fname:
        source_path = Path(fname)
    else:
        source_path = Path(__file__).resolve().parents[1] / 'live' / 'data' / 'source' / fname

    while True:
        with source_path.open('r', encoding='utf-8') as f:
            lines = f.readlines()
            new_lines = lines[start:]  # 新しい行だけ取得

            for line in new_lines:
                line = line.strip()
                if line:
                    race.handle(line)

            prev_start, start = start, len(lines)  # 前回のstartを保存し、今回のstartを更新

        # ファイルが更新されていた場合のみplotを実行
        if start != prev_start:
            order = sorted(
                race.get_laptime_map().keys(),
                key=lambda car: race.get_laptime_map()[car][max(race.get_laptime_map()[car].keys())].get_position()
            )
            plotter.plot_tyres(race.get_stints_map(), order)
            plotter.plot_gap_to_ahead(race.get_laptime_map(), "gap_ahead", 6)
            plotter.plot_gap_to_top(race.get_laptime_map(), "gap_top", 30)
            plotter.plot_positions(race.get_laptime_map(), "position")
            plotter.plot_laptime(race.get_laptime_map(), "laptime", 7)
            plotter.plot_laptime_diff(race.get_laptime_map(), order, "laptime_diffs")

            plotter.plot_weather(race.get_weather_map())
        else:
            log.info("plot is skipped")
        try:
            (logs_path / 'timestamp.txt').unlink()
        except FileNotFoundError:
            pass
        util.write_to_file_top(str(logs_path / 'timestamp.txt'), f"{datetime.datetime.now()}")
        time.sleep(60)


if __name__ == "__main__":
    __main()
