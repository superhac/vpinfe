from threading import Thread, Event
from pinlog import get_logger
from pauseabletask import PauseableTask

class PauseableTasksManager():
    logger = None

    def __init__(self):
        global logger
        logger = get_logger()

        self._tasks = {}
        logger.debug("PauseableTasksManager initialized.")

    def has(self, name):
        return name in self._tasks

    def get(self, name):
        if self.has(name):
            return self._tasks[name]
        logger.warning(f"PauseableTask \"{name}\" doesn't exist.")
        return None

    def add(self, name, target_func):
        if self.has(name):
            logger.error(f"PauseableTask \"{name}\" already exists.")
            return
        pauseable_task_instance = PauseableTask(name, target_func)
        # Store both the Thread object and the PauseableTask instance
        thread_obj = Thread(target=pauseable_task_instance.start, name=name)
        self._tasks[name] = (thread_obj, pauseable_task_instance)
        logger.debug(f"PauseableTask \"{name}\" added.")

    def remove(self, name):
        if self.has(name):
            self.stop(name)
            del self._tasks[name]
            logger.debug(f"PauseableTask \"{name}\" removed.")
            return
        logger.error(f"PauseableTask \"{name}\" doesn't exist.")

    def start(self, name=None):
        if name is None:
            logger.debug("Starting all PauseableTasks.")
            for task_name, (task_thread, _) in self._tasks.items():
                if not task_thread.is_alive():
                    task_thread.start()
            return
        task_data = self.get(name)
        if task_data is None:
            return
        task_thread, _ = task_data # Unpack the thread
        if not task_thread.is_alive():
            task_thread.start()
        else:
            logger.debug(f"PauseableTask \"{name}\" is already running.")

    def _apply_to_tasks(self, name, action_func, action_verb):
        # Applies a given action function to a single task or all tasks.
        if name is None:
            logger.debug(f"{action_verb.capitalize()}ing all PauseableTasks.")
            for task_name, (task_thread, pauseable_task_instance) in self._tasks.items():
                action_func(pauseable_task_instance, task_thread)
        else:
            task_data = self.get(name)
            if task_data is None:
                return
            task_thread, pauseable_task_instance = task_data # Unpack both instances
            action_func(pauseable_task_instance, task_thread)

    def is_paused(self, name):
        task_data = self.get(name)
        if task_data is None:
            return False
        _, pauseable_task_instance = task_data
        return pauseable_task_instance.is_paused()

    def pause(self, name=None):
        self._apply_to_tasks(name, lambda p_task, t_thread: p_task.pause(), "paus")

    def resume(self, name=None):
        self._apply_to_tasks(name, lambda p_task, t_thread: p_task.resume(), "resum")

    def sleep(self, name, duration):
        self._apply_to_tasks(name, lambda p_task, t_thread: p_task.sleep(duration), "sleep")

    def wait(self, name=None):
        self._apply_to_tasks(name, lambda p_task, t_thread: p_task.wait(), "wait")

    def stop(self, name=None):
        def stop_action(p_task, t_thread):
            p_task.stop()
            if t_thread.is_alive():
                t_thread.join(timeout=2)
                if t_thread.is_alive():
                    logger.warning(f"PauseableTask \"{p_task._name}\" did not stop gracefully.")
        self._apply_to_tasks(name, stop_action, "stop")
