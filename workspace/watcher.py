import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
from typing import Callable

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback

    def on_modified(self, event):
        if not event.is_directory:
            self.callback(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.callback(event.src_path)

class WorkspaceWatcher:
    def __init__(self, workspace_path: Path, on_change: Callable[[str], None]):
        self.path = workspace_path
        self.observer = Observer()
        self.handler = CodeChangeHandler(on_change)

    def start(self):
        self.observer.schedule(self.handler, str(self.path), recursive=True)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()