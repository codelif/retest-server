import threading
import shutil
from typing import Any
import time


class StyledThread(threading.Thread):
    """StyledThread class.

    Inherits python's threading.Thread class. Adds changes to return target value and styled waiting.
    """

    def __init__(
        self, group=None, target=None, name=None, args=(), kwargs={}, Verbose=None
    ):
        threading.Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None

    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self, *args):
        threading.Thread.join(self, *args)
        return self._return

    def styled_join(
        self, description: str, dot_interval: float = 0.25, dot_style: str = "."
    ) -> Any:
        """Waits for thread termination with waiting animation. Returns target return value

        Args:
            description (str): Text in waiting animation
            dot_interval (float, optional): Animation speed. Defaults to 0.5.
            dot_style (str, optional): Character to use in animation. Defaults to "."

        Returns:
            Any: Target's return value
        """
        dot_count = 0
        while self.is_alive():
            if dot_count > 3:
                dot_count = 0
            text = description + (dot_style * dot_count)
            remaining_term_columns = shutil.get_terminal_size().columns - len(text) - 1

            print(text, remaining_term_columns * " ", end="\r")

            dot_count += 1
            time.sleep(dot_interval)

        print(" " * shutil.get_terminal_size().columns, end="\r")

        return self.join()
