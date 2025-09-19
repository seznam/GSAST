import tempfile
from time import time
from typing import Callable


class ProjectFetchStatusUpdater:
    def __init__(self, update_interval: int, update_callback: Callable):
        self.update_interval = update_interval
        self.status_file = tempfile.NamedTemporaryFile(mode='w+t', delete=False)
        self.last_status_update = time()
        self.update_callback = update_callback

    def update_status(self):
        if time() - self.last_status_update >= self.update_interval:
            self.status_file.seek(0)
            message_text = self.status_file.readlines()[-1]
            self.last_status_update = time()
            self.update_callback(message_text)
