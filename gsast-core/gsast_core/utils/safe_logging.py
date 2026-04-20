import sys
import logging
import re

import tqdm


class SensitiveFormatter(logging.Formatter):
    """
    This formatter removes URL credentials from logs
    """
    @staticmethod
    def _filter(s):
        return re.sub(r'://(.*?)@', r'://', s)

    def format(self, record):
        original = logging.Formatter.format(self, record)
        return self._filter(original)


class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            sys.stdout.flush()
            self.flush()
        except Exception:
            self.handleError(record)


LOG_FORMAT = '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
logging.basicConfig(level=logging.INFO, datefmt='%d/%b/%Y %H:%M:%S')

log = logging.getLogger()
log.addHandler(TqdmLoggingHandler())
log.propagate = False

for handler in logging.root.handlers:
    handler.setFormatter(SensitiveFormatter(fmt=LOG_FORMAT))
