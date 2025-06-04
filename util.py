import os
from logging import Logger

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure


def join_with_colon(*args):
    return ' : '.join(args)


def save(fig: Figure, ax: Axes, path: str, log: Logger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.tight_layout()
    ax.grid(True)
    fig.savefig(path, bbox_inches='tight')
    log.info(f"Saved plot to {path}")
    plt.close(fig)


def write_to_file_top(filepath: str, content: str):
    """
    ファイルの先頭に文字列を書き込みます。
    ファイルが存在しなければ新しく作成します。

    Parameters:
    - filepath: 書き込み対象のファイルパス
    - content: 先頭に書き込む文字列（末尾に改行は自動で追加）
    """
    content += '\n'

    if os.path.exists(filepath):
        # 既存ファイルの内容を読み込んでから先頭に書き込む
        with open(filepath, 'r', encoding='utf-8') as file:
            original = file.read()
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(content + original)
    else:
        # ファイルがなければ新規作成して書き込む
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(content)
