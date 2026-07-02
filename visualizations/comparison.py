import os
from logging import Logger
from typing import Any

import fastf1
import matplotlib.pyplot as plt
from fastf1.core import Session
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("execute")
def execute(session: Session, log: Logger, comparison: list[list[dict[str, Any]]]):
    _plot_driver_lap_telemetry(session, log, comparison,
                               key='throttle',
                               label='Throttle [%]',
                               value_func=lambda data: data.Throttle
                               )
    _plot_driver_lap_telemetry(session, log, comparison,
                               key='brake',
                               label='Brake',
                               value_func=lambda data: data.Brake.astype(float)
                               )
    _plot_driver_lap_telemetry(session, log, comparison,
                               key='drs',
                               label='DRS',
                               value_func=lambda data: data.DRS.astype(float)
                               )
    _plot_driver_lap_telemetry(session, log, comparison,
                               key='speed',
                               label='Speed',
                               value_func=lambda data: data.Speed.astype(float)
                               )


@tracer.start_as_current_span("_plot_driver_lap_telemetry")
def _plot_driver_lap_telemetry(session: Session, log: Logger, comparison: list[list[dict[str, Any]]], key: str, label,
                               value_func):
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    z = {}
    for targets in comparison:
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        v_min, v_max = float('inf'), float('-inf')
        for c in targets:
            if 'Fastest' in c and c['Fastest']:
                lap = session.laps.pick_drivers(c['Driver']).pick_fastest()
            elif 'Driver' in c:
                laps = session.laps.pick_drivers(c['Driver']).pick_laps(c['LapNumber'])
                if laps.empty:
                    continue
                lap = laps.iloc[0]
            else:
                continue
            if lap is None or lap.empty:
                continue
            car_data = lap.get_car_data().add_distance()
            label = f"{lap.Driver} {lap.LapNumber} {lap.LapTime.total_seconds()}"
            try:
                team_color = fastf1.plotting.get_team_color(lap.Team, session)
            except AttributeError:
                team_color = 'gray'
            camera_color = constants.camera[session.event.year].get(int(lap.DriverNumber), 'black')
            if lap.DriverNumber in z and z[lap.DriverNumber] == 0:
                line_style = 'dotted'
            elif lap.DriverNumber in z and z[lap.DriverNumber] == 1:
                line_style = 'dashdot'
            else:
                line_style = 'solid' if camera_color == 'black' else 'dashed'
            if lap.DriverNumber not in z:
                z[lap.DriverNumber] = 0
            else:
                z[lap.DriverNumber] += 1
            y_data = value_func(car_data)
            ax.plot(car_data.Distance, y_data, label=label, linewidth=1, color=team_color, linestyle=line_style,
                    alpha=0.5)
            v_min, v_max = min(v_min, y_data.min()), max(v_max, y_data.max())

        if v_min == float('inf') or v_max == float('-inf') or (v_min == 0.0 and v_max == 0.0):
            continue

        for _, corner in circuit_info.corners.iterrows():
            ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
            ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05, f"{corner.Number}{corner.Letter}",
                    va='center_baseline', ha='center', size='small')

        ax.set_ylim(v_min - 0.1 * (v_max - v_min), v_max + 0.1 * (v_max - v_min))
        ax.set_ylabel(label)
        ax.set_xlabel("Distance [m]")
        ax.grid(True)
        ax.legend(loc='upper right', fontsize='small')
        plt.tight_layout()

        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/{key}/comparison/{'_'.join([c['Driver'] for c in targets])}.png"
        )
        ax.grid(True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)
