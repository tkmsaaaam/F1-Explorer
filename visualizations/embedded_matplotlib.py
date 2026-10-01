"""Translate the single-axis session charts into offline Plotly figure data.

Only the artists used by session reports are supported. No raster image is
rendered, and unsupported artists fail explicitly instead of disappearing.
"""

from __future__ import annotations

import matplotlib.colors as colors
import matplotlib.dates as dates
from matplotlib.collections import LineCollection, PathCollection
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator
from matplotlib.text import Annotation
import numpy as np
import plotly.graph_objects as go


def _color(value: object) -> str:
    red, green, blue, alpha = colors.to_rgba(value)
    return f"rgba({round(red * 255)},{round(green * 255)},{round(blue * 255)},{alpha})"


def embed_matplotlib(fig) -> go.Figure:
    """Preserve data, limits, labels, and map annotations without writing PNG."""
    if len(fig.axes) != 1:
        raise ValueError("Embedded session charts require a single axis")
    ax = fig.axes[0]
    if ax.images:
        raise ValueError("Raster artists cannot be embedded as graph data")
    result = go.Figure()
    x_dates = (isinstance(ax.xaxis.get_major_formatter(), dates.DateFormatter)
               or isinstance(ax.xaxis.get_major_locator(), dates.DateLocator))
    dash = {"--": "dash", ":": "dot", "-.": "dashdot", "-": "solid"}
    legend = ax.get_legend()
    labels: set[str] = set()

    def x_values(values):
        array = np.asarray(values)
        if x_dates and np.issubdtype(array.dtype, np.number):
            return [dates.num2date(value).isoformat() for value in array]
        return values

    for line in ax.lines:
        label = line.get_label()
        visible_label = legend is not None and not label.startswith("_") and label not in labels
        labels.add(label)
        x = line.get_xdata(orig=False)
        y = line.get_ydata(orig=False)
        if line.get_transform() == ax.get_xaxis_transform():
            low, high = ax.get_ylim()
            y = low + np.asarray(y) * (high - low)
        elif line.get_transform() == ax.get_yaxis_transform():
            low, high = ax.get_xlim()
            x = low + np.asarray(x) * (high - low)
        result.add_trace(go.Scatter(
            x=x_values(x), y=y, mode="lines", name=label,
            showlegend=visible_label,
            line=dict(color=_color(line.get_color()), width=line.get_linewidth(),
                      dash=dash.get(line.get_linestyle(), "solid")),
        ))

    for collection in ax.collections:
        if isinstance(collection, LineCollection):
            segments = collection.get_segments()
            palette = collection.get_colors()
            widths = collection.get_linewidths()
            for index, segment in enumerate(segments):
                result.add_trace(go.Scatter(
                    x=x_values(segment[:, 0]), y=segment[:, 1], mode="lines",
                    showlegend=False,
                    line=dict(color=_color(palette[index % len(palette)]),
                              width=float(widths[index % len(widths)])),
                ))
        elif isinstance(collection, PathCollection):
            points = collection.get_offsets()
            faces = collection.get_facecolors()
            edges = collection.get_edgecolors()
            sizes = collection.get_sizes()
            widths = collection.get_linewidths()
            result.add_trace(go.Scatter(
                x=x_values(points[:, 0]), y=points[:, 1], mode="markers", showlegend=False,
                marker=dict(
                    size=[float(np.sqrt(sizes[i % len(sizes)])) for i in range(len(points))],
                    color=[_color(faces[i % len(faces)]) for i in range(len(points))],
                    line=dict(color=[_color(edges[i % len(edges)]) for i in range(len(points))],
                              width=float(widths[0])),
                ),
            ))
        else:
            raise ValueError(f"Unsupported session chart collection: {type(collection).__name__}")

    for patch in ax.patches:
        if not isinstance(patch, Rectangle):
            raise ValueError(f"Unsupported session chart patch: {type(patch).__name__}")
        result.add_shape(
            type="rect", x0=patch.get_x(), x1=patch.get_x() + patch.get_width(),
            y0=patch.get_y(), y1=patch.get_y() + patch.get_height(),
            fillcolor=_color(patch.get_facecolor()),
            line=dict(color=_color(patch.get_edgecolor()), width=patch.get_linewidth()),
            layer="below",
        )

    for text in ax.texts:
        x, y = text.xy if isinstance(text, Annotation) else text.get_position()
        result.add_annotation(
            x=x_values([x])[0], y=y, text=text.get_text(), showarrow=False,
            font=dict(size=text.get_fontsize(), color=_color(text.get_color())),
            xanchor={"left": "left", "right": "right"}.get(text.get_ha(), "center"),
            yanchor={"top": "top", "bottom": "bottom"}.get(text.get_va(), "middle"),
            xshift=text.get_position()[0] if isinstance(text, Annotation) and text.anncoords == "offset points" else 0,
            yshift=text.get_position()[1] if isinstance(text, Annotation) and text.anncoords == "offset points" else 0,
        )

    # Include explicitly supplied legend handles, e.g. tyre compounds and N/U.
    if legend is not None:
        for handle, text in zip(legend.legend_handles, legend.get_texts()):
            label = text.get_text()
            if label in labels:
                continue
            color = handle.get_facecolor() if isinstance(handle, Rectangle) else handle.get_color()
            result.add_trace(go.Scatter(x=[None], y=[None], name=label,
                                       mode="markers", marker=dict(color=_color(color))))

    result.update_layout(
        title=ax.get_title(), template="plotly_white",
        xaxis=dict(title=ax.get_xlabel(), range=list(x_values(ax.get_xlim())),
                   visible=ax.axison, showgrid=any(line.get_visible() for line in ax.get_xgridlines())),
        yaxis=dict(title=ax.get_ylabel(), range=list(ax.get_ylim()),
                   visible=ax.axison, showgrid=any(line.get_visible() for line in ax.get_ygridlines())),
    )
    if x_dates:
        result.update_xaxes(type="date", tickformat="%H:%M")
    for name, axis in (("xaxis", ax.xaxis), ("yaxis", ax.yaxis)):
        if isinstance(axis.get_major_locator(), FixedLocator):
            result.layout[name].update(tickmode="array", tickvals=list(axis.get_ticklocs()),
                                       ticktext=[text.get_text() for text in axis.get_ticklabels()])
    if ax.get_aspect() == 1.0:
        result.update_yaxes(scaleanchor="x", scaleratio=1)
        result.update_layout(meta=dict(f1ExplorerKind="trackMap"))
    return result
