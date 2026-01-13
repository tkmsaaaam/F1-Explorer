import os
from logging import Logger

import fastf1
import fastf1.plotting
from fastf1.core import Session, Laps
from matplotlib import pyplot as plt
from opentelemetry import trace

import constants
from visualizations.domain.driver import Driver
from visualizations.domain.stint import Stint

tracer = trace.get_tracer(__name__)


def make_stint_set(min_consecutive_laps: int, all_laps: Laps, compound: str) -> set[Stint]:
    stints = set()
    laps: Laps = all_laps[all_laps.Compound == compound]
    grouped_by_driver = laps.sort_values(by='TyreLife').groupby(['DriverNumber', 'Stint'])
    for (driver_number_str, _), stint_laps in grouped_by_driver:
        driver_number = int(driver_number_str)
        if len(stint_laps) < min_consecutive_laps:
            continue
        first_lap = stint_laps.iloc[0]
        lap_map: dict[int, float] = {}
        for i in range(0, len(stint_laps)):
            if stint_laps.iloc[i].LapTime.total_seconds() > all_laps.LapTime.min().total_seconds() * 1.2:
                continue
            lap_map[stint_laps.iloc[i].TyreLife] = stint_laps.iloc[i].LapTime.total_seconds()
        driver: Driver = Driver(driver_number, first_lap.Driver, first_lap.Team)
        stint: Stint = Stint(compound, lap_map, driver)
        stints.add(stint)
    return stints


@tracer.start_as_current_span("plot_by_tyre_age_and_tyre")
def plot_by_tyre_age_and_tyre(session: Session, log: Logger):
    """
    タイヤ別のファイルにロングランのラップタイム(y)推移をタイヤエイジ(x)でプロットする
    Args:
        session: プロットするセッション
        log: ロガー

    """
    min_consecutive_laps = 2  # ロングランとみなす連続ラップ数のしきい値

    all_laps: Laps = session.laps

    compounds = all_laps.Compound.unique()
    for compound in compounds:
        fastf1.plotting.setup_mpl(mpl_timedelta_support=True, misc_mpl_mods=False, color_scheme='light')
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        stint_set = make_stint_set(min_consecutive_laps, all_laps, compound)
        legends = set()
        for stint in stint_set:
            color = fastf1.plotting.get_team_color(stint.driver.team_name, session)
            x = sorted(stint.laps.keys())
            y = [stint.laps.get(i) for i in x]
            line_style = "solid" if constants.camera[session.event.year].get(stint.driver.number, 'black') == "black" else "dashed"
            if stint.driver.number in legends:
                ax.plot(x, y, linewidth=1, color=color, linestyle=line_style)
            else:
                ax.plot(x, y, linewidth=1, color=color, label=stint.driver.name, linestyle=line_style)
                legends.add(stint.driver.number)
        ax.legend(fontsize='small')
        ax.invert_yaxis()
        ax.grid(True)
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/long_runs/{compound}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)
