"""Lazy registry for official database adapters."""

from importlib import import_module


_DRIVERS = {
    "sqlite": "separan.db.drivers.sqlite",
    "postgresql": "separan.db.drivers.postgresql",
    "mysql": "separan.db.drivers.mysql",
    "oracle": "separan.db.drivers.oracle",
    "sqlserver": "separan.db.drivers.sqlserver",
}


def known_drivers():
    return frozenset(_DRIVERS)


def get_driver(name):
    module_name = _DRIVERS.get(name)
    if module_name is None:
        return None
    return import_module(module_name).ADAPTER
