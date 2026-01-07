import sys
import logging
from debug.time_utils import format_current_stamp

class _TicksHandler(logging.Handler):
    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self.setFormatter(logging.Formatter("%(ts)s\t[%(levelname)8s]\t%(name)s:\t%(message)s"))

    def emit(self, record):
        record.ts = format_current_stamp()
        sys.stdout.write(self.format(record) + "\n")

def setup_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in list(getattr(root_logger, "handlers", ())):
        root_logger.removeHandler(handler)

    root_logger.addHandler(_TicksHandler(level))

setup_logging()

APP = logging.getLogger("APP")
BLE = logging.getLogger("BLE")
PRT = logging.getLogger("PRT")
