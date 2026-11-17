"""Background worker that runs the whole job without freezing the console.

Every step goes through sleep(), wait_until() or checkpoint(). Those are the places
where PAUSE blocks the worker and STOP ends it.
"""
import os
import threading
import time
import traceback

import actions
import launcher
import login
import winutil
import goals
from errors import Stopped, StepFailed


GOAL_TIMEOUT = 900     # seconds one goal may take before the bot gives up
MAX_FAILURES = 3       # failed passes in a row before the goal is abandoned


class Automation:
    def __init__(self, log, set_action, on_done, launcher_path, area):
        self.log = log                  # callable: log(message, level)
        self.set_action = set_action    # callable: set_action(text)
        self.on_done = on_done          # called once when the job ends, whatever the reason
        self.launcher_path = launcher_path
        self.area = area                # (x, y, w, h) of the free space right of the console
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread = None
        self.action = actions.IDLE      # the current goal; the loops below run while it stays unchanged

    # ----- control, called from the GUI thread -----
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._resume.set()  # wake the worker if it is paused

    def pause(self):
        self._resume.clear()

    def resume(self):
        self._resume.set()

    def stopping(self):
        return self._stop.is_set()

    # ----- helpers used by the steps -----
    def checkpoint(self):
        """Raises Stopped after STOP and blocks while paused. Returns the seconds spent paused."""
        if self._stop.is_set():
            raise Stopped()
        paused = 0.0
        if not self._resume.is_set():
            started = time.monotonic()
            self._resume.wait()
            paused = time.monotonic() - started
        if self._stop.is_set():
            raise Stopped()
        return paused

    def sleep(self, seconds):
        """Sleeps while still reacting to PAUSE and STOP. Returns the seconds spent paused."""
        end = time.monotonic() + seconds
        paused_total = 0.0
        while True:
            paused_total += self.checkpoint()
            remaining = end + paused_total - time.monotonic()
            if remaining <= 0:
                return paused_total
            time.sleep(min(0.05, remaining))

    def wait_until(self, check, timeout, interval=0.7):
        """Calls check() repeatedly until it returns a truthy value, which is then returned.
        Returns None on timeout. Time spent paused does not count towards the timeout."""
        end = time.monotonic() + timeout
        while True:
            end += self.checkpoint()
            value = check()
            if value:
                return value
            if time.monotonic() >= end:
                return None
            end += self.sleep(interval)
    

    # ----- goals -----
    def _set_goal(self, title):
        self.action = title
        self.set_action(title)

    def pursue(self, goal):
        """Works on one goal until it is verified as done.
        The goal is re-checked from the screen on every pass, so the bot never assumes a step worked."""
        self._set_goal(goal.title)
        started = time.monotonic()
        failures = 0
        while self.action == goal.title:
            started += self.checkpoint()
            if goal.is_done(self):
                self.log(f"Goal done: {goal.title}", "OK")
                return
            if time.monotonic() - started > GOAL_TIMEOUT:
                raise StepFailed(f"Goal not reached in time: {goal.title}")
            try:
                goal.step(self)
                failures = 0
            except StepFailed as err:
                failures += 1
                if failures >= MAX_FAILURES:
                    raise
                self.log(f"{err} Trying again ({failures}/{MAX_FAILURES - 1})...", "WARN")
                self.sleep(2.0)


    # ----- the job itself -----
    def _run(self):
        try:
            self._workflow()
        except Stopped:
            self.log("Automation stopped.", "WARN")
        except StepFailed as err:
            self.log(str(err), "ERROR")
        except Exception as err:  # an unexpected bug: show it in the log and in the terminal
            self.log(f"Unexpected error: {type(err).__name__}: {str(err)[:200]}", "ERROR")
            traceback.print_exc()
        finally:
            self.set_action(actions.IDLE)
            self.on_done()

    def _workflow(self):
        count = winutil.minimize_all(skip_pid=os.getpid())
        self.log(f"Minimized {count} window(s).")
        launcher.open_and_arrange(self, self.launcher_path)
        account, _ = login.load_account()
        self.pursue(goals.LoginGoal(account))
        self.log("Next goals (mails, events, Peer Arena, Quest Board, Guild Dailies) are not built yet. "
                 "Stopping here so you can test.", "OK")