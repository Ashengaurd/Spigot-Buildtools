import logging
import os
import re
from sys import platform
from datetime import datetime
from queue import Queue
from subprocess import Popen, PIPE
from threading import Thread
from time import sleep
from typing import List
from zipfile import ZipFile

# Default to Windows
runnable_extension = "bat"
remove_directory_cmd = 'RD /s /q "%path%"\n'
remove_file_cmd = 'DEL /q "%path%"\n'

# linux
if platform == "linux" or platform == "linux2":
    runnable_extension = "sh"
    remove_directory_cmd = 'rm -r "%path%"\n'
    remove_file_cmd = 'rm "%path%"\n'
# mac
elif platform == "darwin":
    runnable_extension = "sh"
    remove_directory_cmd = 'rm -r "%path%"\n'
    remove_file_cmd = 'rm "%path%"\n'
# windows
elif platform == "win32":
    # do nothing because Windows is the default
    pass

CONSOLE = 15
logging.addLevelName(CONSOLE, "CONSOLE")
CONSOLE_ERROR = 45
logging.addLevelName(CONSOLE_ERROR, "CONSOLE_ERROR")


def console(self, message, *args, **kws):
    if self.isEnabledFor(CONSOLE):
        self._log(CONSOLE, message, args, **kws)


def console_error(self, message, *args, **kws):
    if self.isEnabledFor(CONSOLE):
        self._log(CONSOLE_ERROR, message, args, **kws)


logging.Logger.console = console
logging.Logger.console_error = console_error


class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


class BatchExecutor:
    def __init__(self, name, path, logger: logging.Logger):
        self.name = name
        self.path = path
        self.logger = logger

    def read_error(self, process: Popen, error: Queue):
        while True:
            output = str(process.stderr.readline())[2:-1].replace("\\r", "").replace("\\n", "").replace("\\t", "  ").replace("\\\\", "\\")
            if process.poll() is not None and output == '':
                break
            if output:
                error.put(output)

    def run(self):
        errors = Queue()
        process = Popen(self.name, cwd=self.path, stdout=PIPE, stderr=PIPE, shell=True)
        Thread(target=self.read_error, args=[process, errors], daemon=True).start()
        while True:
            output = str(process.stdout.readline())[2:-1].replace("\\r", "").replace("\\n", "").replace("\\t", "  ").replace("\\\\", "\\")
            if process.poll() is not None and output == '':
                break
            if output:
                self.logger.console(output)

        if not errors.empty():
            self.logger.error("Worker found following errors while building. The build might be unusable")
            while True:
                try:
                    self.logger.console_error(errors.get(False))
                except Exception:
                    break
        sleep(3)


class Version:
    def __init__(self, version):
        self.v = version
        self._minor = int(re.findall('\d+', self.v)[1])

        from main import PATH
        self.path = f'{PATH}/BuildTools/{self.v.replace(".", "_")}'
        self.command = f'java -jar BuildTools.jar --rev {version} --output-dir ./../'
        self.craftbukkit = False

    def __repr__(self):
        return self.v

    def __str__(self):
        return self.v

    def save_batch(self):
        os.makedirs(self.path, exist_ok=True)
        with open(f'{self.path}/Installer.{runnable_extension}', 'w', encoding='utf8') as f:
            f.write('@echo off\n')
            f.write(self.command)
            if self.craftbukkit and self._minor > 13:
                f.write(f'\n{self.command} --compile craftbukkit')

        from main import TOOLS
        with open(f'{self.path}/Cleaner.{runnable_extension}', 'w', encoding='utf8') as f:
            f.write('@echo off\n')
            for file in TOOLS:
                path = f'{self.path}/{file}'.replace('/', '\\')
                # TODO: change per OS
                if os.path.isdir(path):
                    f.write(remove_directory_cmd.replace("%path%", path))
                else:
                    f.write(remove_file_cmd.replace("%path%", path))

    def extract_tools(self):
        os.makedirs(self.path, exist_ok=True)
        with ZipFile(f'./tools.zip') as file:
            file.extractall(self.path)

        self._cache = os.listdir(self.path)

    def run_batch(self, logger: logging.Logger):
        BatchExecutor(f'Installer.{runnable_extension}', self.path, logger).run()

    def clear_tools(self, logger: logging.Logger):
        BatchExecutor(f'Cleaner.{runnable_extension}', self.path, logger).run()
        os.remove(f'{self.path}/Installer.{runnable_extension}')
        os.remove(f'{self.path}/Cleaner.{runnable_extension}')


class Worker:
    _WORKERS: List['Worker'] = []

    def __init__(self, app, queue: Queue):
        count = len(Worker._WORKERS)
        self.name = f'Worker-{count + 1}'
        self._thread = Thread(target=self.build, daemon=True)
        self._closed = True
        self.queue = queue
        self.log_queue = Queue()
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        self.idle = False

        form = logging.Formatter(f'%(asctime)s: %(message)s', "%H:%M:%S")
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(form)
        self.logger.addHandler(self.queue_handler)

        from GUI import LoggerUI
        self.frame = LoggerUI(app, self.log_queue, self.queue_handler, name=self.name)
        self.frame.grid(column=count % 3, row=count // 3, padx=5, pady=5)

        Worker._WORKERS.append(self)

    def start(self):
        self._closed = False
        self._thread.start()
        self.logger.info(f'Worker has been activated.')

    def close(self):
        if not self.idle:
            self.logger.critical("Your request has been awaited until worker finishes the build.")
        self._closed = True

    def build(self):
        sleep(0.5)
        while not self._closed:
            try:
                if not self.idle:
                    self.logger.debug(f'Worker is looking for a task.')
                    self.idle = True
                version: Version = self.queue.get(True, 0.2)
                self.logger.debug(f'Worker acquired {version} as its build task.')
                start = datetime.now()
                self.idle = False
            except Exception:
                continue

            version.save_batch()
            version.extract_tools()
            self.logger.debug(f'Worker extracted all tools required and started the build for {version}.')
            version.run_batch(self.logger)
            self.logger.debug(f'Worker finished the build and now is clearing the cache.')
            version.clear_tools(self.logger)
            time = str(datetime.now() - start).split('.')[0]
            self.logger.info(f'Worker has finished his build task for {version}. It took {time}.')
        self.logger.warning("Worker is now fired")
        sleep(5)
        self.frame.destroy()

    @staticmethod
    def add(app, queue):
        Worker(app, queue).start()

    @staticmethod
    def close_last():
        worker = Worker._WORKERS.pop()
        worker.close()

    @staticmethod
    def get_all():
        return Worker._WORKERS.copy()
