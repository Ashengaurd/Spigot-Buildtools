import logging
import os
from queue import Queue
from typing import List
from zipfile import ZipFile

import yaml

from GUI import APP
from classes import Version

logging.basicConfig(level=logging.DEBUG)
with open('./config.yml', 'r') as f:
    CONFIG = yaml.safe_load(f.read())

PATH = os.path.abspath('')
QUEUE = Queue()
VERSIONS: List[Version] = [Version(str(ver)) for ver in CONFIG.get('AvailableVersions')]
MAX_THREAD = CONFIG.get('StartingWorkers')
TOOLS = []

with ZipFile('tools.zip') as z:
    files = z.namelist()
    for file in files:
        if file.find('/') == -1:
            TOOLS.append(file)
        else:
            file = file[:file.find('/')]
            if file not in TOOLS:
                TOOLS.append(file)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app = APP(QUEUE)
    app.start()
