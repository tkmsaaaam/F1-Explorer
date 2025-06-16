from logging import Logger

import fastf1
import fastf1.plotting
from fastf1.core import Session
from matplotlib import pyplot as plt

import config
import util


def plot_by_tyre_age_and_tyre(session: Session, log: Logger):
    """
    タイヤ別のファイルにロングランのラップタイム(y)推移をタイヤエイジ(x)でプロットする
    Args:
        session: プロットするセッション
        log: ロガー

    Returns:

    """
    min_consecutive_laps = 2  # ロングランとみなす連続ラップ数のしきい値

    all_laps = session.laps

    compounds = all_laps.Compound.unique()
    for compound in compounds:
        # プロット準備
        fastf1.plotting.setup_mpl(mpl_timedelta_support=True, misc_mpl_mods=False, color_scheme='light')
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
        laps = all_laps[all_laps.Compound == compound]
        grouped_by_driver = laps.groupby(['DriverNumber', 'Stint'])
        legends = []
        for (driver_number_str, stint_num), stint_laps in grouped_by_driver:
            driver_number = int(driver_number_str)
            if len(stint_laps) < min_consecutive_laps:
                continue
            driver_name = stint_laps.Driver.iloc[0]
            color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
            stint_laps = stint_laps.sort_values(by='TyreLife')
            y = []
            x = []
            for i in range(0, len(stint_laps)):
                if stint_laps.LapTime.iloc[i].total_seconds() > all_laps.LapTime.min().total_seconds() * 1.2:
                    continue
                x.append(stint_laps.TyreLife.iloc[i])
                y.append(stint_laps.LapTime.iloc[i].total_seconds())
            line_style = "solid" if config.camera_info_2025.get(driver_number, 'black') == "black" else "dashed"
            if driver_number in legends:
                ax.plot(x, y, linewidth=0.75, color=color, linestyle=line_style)
            else:
                ax.plot(x, y, linewidth=0.75, color=color, label=driver_name, linestyle=line_style)
                legends.append(driver_number)
        ax.legend(loc='upper right', fontsize='small')
        ax.invert_yaxis()
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/long_runs/{compound}.png"
        util.save(fig, ax, output_path, log)
