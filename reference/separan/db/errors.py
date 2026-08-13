"""Internal database-adapter failures translated by the Separan DB core."""


class AdapterError(Exception):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category
        self.message = message


class DriverNotInstalled(AdapterError):
    def __init__(self, driver, extra):
        self.driver = driver
        self.extra = extra
        super().__init__(
            "db_driver_error",
            "Database driver is not installed.\n\n"
            f"Driver:\n{driver}\n\nInstall with:\n"
            f'pip install "separan-lang[{extra}]"',
        )
