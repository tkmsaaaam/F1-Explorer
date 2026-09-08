"""Race-start samples on a shared clock, with driver-local distance origins."""

import numpy as np
import pandas as pd


def start_samples(session, driver, *, until_turn1=False, circuit_info=None):
    """Return samples and a corner distance, or None when evidence is missing.

    Session status defines lights-out. Integrate speed from that instant; locate
    T1 using the first lap's position feed, not a flying lap's distance origin.
    No grid-spacing assumptions or fastest-lap fallbacks are used.
    """
    start = session.session_start_time
    if start is None or pd.isna(start):
        return None
    car = session.car_data.get(str(driver))
    if car is None or not {"SessionTime", "Speed"}.issubset(car.columns):
        return None
    samples = pd.DataFrame({
        "TimeSeconds": (car.SessionTime - start).dt.total_seconds(),
        "Speed": pd.to_numeric(car.Speed, errors="coerce"),
    }).replace([np.inf, -np.inf], np.nan).dropna()
    samples = samples.sort_values("TimeSeconds").drop_duplicates("TimeSeconds")
    if len(samples) < 2 or samples.TimeSeconds.iloc[0] > 0:
        return None
    end = 10.0
    if until_turn1:
        laps = session.laps.pick_drivers(driver)
        first = laps[laps.LapNumber == 1]
        position = session.pos_data.get(str(driver))
        circuit = circuit_info if circuit_info is not None else session.get_circuit_info()
        if first.empty or position is None or circuit is None or circuit.corners.empty:
            return None
        corners = circuit.corners.sort_values("Distance")
        corner = corners.iloc[0]
        if not {"SessionTime", "X", "Y"}.issubset(position.columns):
            return None
        position = position.dropna(subset=["SessionTime", "X", "Y"])
        position = position[(position.SessionTime >= start) &
                            (position.SessionTime <= first.iloc[0].Time)]
        pit_out = first.iloc[0].get("PitOutTime", pd.NaT)
        if pd.notna(pit_out) and pit_out > start:
            position = position[position.SessionTime >= pit_out]
        if "Status" in position:
            position = position[position.Status == "OnTrack"]
        if position.empty or pd.isna(corner.X) or pd.isna(corner.Y):
            return None
        squared_distance = (position.X - corner.X) ** 2 + (position.Y - corner.Y) ** 2
        nearest = squared_distance.idxmin()
        # X/Y are in decimetres. Do not invent a crossing for a DNS/DNF or
        # pit-lane starter whose first lap never reaches this corner.
        if squared_distance.loc[nearest] > 300 ** 2 or nearest in {position.index[0], position.index[-1]}:
            return None
        # Position samples approximate the corner crossing time.
        end = (position.loc[nearest, "SessionTime"] - start).total_seconds()
    if end <= 0 or samples.TimeSeconds.iloc[-1] < end:
        return None
    times = np.concatenate(([0.0], samples.loc[
        (samples.TimeSeconds > 0) & (samples.TimeSeconds < end), "TimeSeconds"
    ].to_numpy(), [end]))
    speeds = np.interp(times, samples.TimeSeconds, samples.Speed)
    distances = np.concatenate(([0.0], np.cumsum(
        np.diff(times) * (speeds[:-1] + speeds[1:]) / 7.2
    )))
    return pd.DataFrame({"TimeSeconds": times, "Speed": speeds, "Distance": distances}), (
        float(distances[-1]) if until_turn1 else None
    )
