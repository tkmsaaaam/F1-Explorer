"""Shared axis range calculations for report charts."""


def bar_range(values):
    """Return a padded non-negative range for time/value bar charts."""
    if not values:
        return None
    low, high = min(values), max(values)
    padding = max((high - low) * 0.08, high * 0.01)
    return [max(0, low - padding), high + padding]
