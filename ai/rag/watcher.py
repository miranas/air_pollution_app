"""
Watchdog – spremlja rag_sources/ in samodejno vektorižira.
"""

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ai.rag.vectorize import  vectorize_file, SUPPORTED_EXTENSIONS


class RAGHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(SUPPORTED_EXTENSIONS):
            print(f"Nov dokument: {event.src_path}")
            try:
                vectorize_file(event.src_path)
            except Exception as e:
                print(f"Napaka: {e}")

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(SUPPORTED_EXTENSIONS):
            print(f"Spremenjen dokument: {event.src_path}")
            try:
                vectorize_file(event.src_path)
            except Exception as e:
                print(f"Napaka: {e}")

    def on_moved(self, event):
        if event.is_directory:
            return
        if event.dest_path.endswith(SUPPORTED_EXTENSIONS):
            print(f"Premaknjen dokument: {event.dest_path}")
            try:
                vectorize_file(event.dest_path)
            except Exception as e:
                print(f"Napaka: {e}")


def start_watcher(folder: str = "rag_sources"):
    observer = Observer()
    observer.schedule(RAGHandler(), folder, recursive=False)
    observer.start()
    print(f"Watchdog spremlja: {folder}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()
