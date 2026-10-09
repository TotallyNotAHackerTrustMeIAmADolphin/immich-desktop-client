import queue
import threading


class GuiRunner:
    """Runs GUI work (tkinter windows) one task at a time on a single thread.

    Tk must not be driven from the tray library's callback threads, and two clicks must not open two
    windows, so tray callbacks only submit tasks and the main thread executes them here.
    With inline=True (platforms where the tray owns the main thread) tasks run immediately instead.
    """

    def __init__(self, inline=False):
        self.__inline = inline
        self.__tasks = queue.Queue()
        self.__pending = set()
        self.__lock = threading.Lock()
        self.__running = True

    def submit(self, task):
        if self.__inline:
            self.__execute(task)
        else:
            self.__tasks.put((None, task))

    def submit_once(self, name, task):
        """Like submit, but ignored while a task with this name is still queued or running."""
        with self.__lock:
            if name in self.__pending:
                return
            self.__pending.add(name)
        if self.__inline:
            self.__execute(task, name)
        else:
            self.__tasks.put((name, task))

    def run(self):
        while self.__running:
            try:
                name, task = self.__tasks.get(timeout=0.2)
            except queue.Empty:
                continue
            self.__execute(task, name)

    def stop(self):
        self.__running = False

    def __execute(self, task, name=None):
        try:
            task()
        except Exception as e:  # a broken window must not take the whole app down
            print(f"GUI task failed: {e!r}")
        finally:
            if name is not None:
                with self.__lock:
                    self.__pending.discard(name)
