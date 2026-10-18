"""Shared backend infrastructure: paths, defaults, settings store, database.

Anything used by more than one part of the app lives here. GenModules must only
depend on `app.common`, never on each other.
"""
