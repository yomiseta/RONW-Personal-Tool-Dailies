"""Background worker that runs the whole job without freezing the console.

Every step goes through sleep(), wait_until() or checkpoint(). Those are the places
where PAUSE blocks the worker and STOP ends it.
"""
import os
import threading
import time
import traceback

import accounts
import actions
import daily_goals
import goals
import launcher
import logbook
import progress
import settings
import winutil
from errors import Halt, Stopped, StepFailed


GOAL_TIMEOUT = 900     # seconds one goal may take before the bot gives up
MAX_FAILURES = 3       # failed passes in a row before the goal is abandoned
CLOSE_WAIT = 20        # seconds the game gets to close by itself before its process is ended


class Automation:
    def __init__(self, log, set_action, on_done, launcher_path, area):
        self._console_log = log         # callable: log(message, level)
        self.log = self._log            # every log line also goes to the log file
        self.set_action = set_action    # callable: set_action(text)
        self.on_done = on_done          # called once when the job ends, whatever the reason
        self.launcher_path = launcher_path
        self.area = area                # (x, y, w, h) of the free space right of the console
        self._logbook = logbook.LogFile()
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread = None
        self.action = actions.IDLE      # the current goal; the loops below run while it stays unchanged

    # ----- logging -----
    def _log(self, message, *level):
        self._logbook.add(message)
        self._console_log(message, *level)

    def _save_log(self):
        """Writes everything shown in the console during this run to the Logs folder,
        together with a screenshot of the game as it was when the run ended."""
        try:
            hwnd = goals.game_window()
        except Exception:
            hwnd = None
        try:
            saved = self._logbook.save(hwnd)
        except OSError as err:
            self._console_log(f"The log file could not be saved: {err}", "WARN")
            return
        if saved:
            log_path, shot_path = saved
            self._console_log(f"Log saved: Logs/{log_path.name}")
            if shot_path:
                self._console_log(f"Screenshot saved: Logs/{shot_path.name}")

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
            if time.monotonic() - started > getattr(goal, "timeout", GOAL_TIMEOUT):
                raise StepFailed(f"Goal not reached in time: {goal.title}")
            try:
                goal.step(self)
                failures = 0
            except Halt:
                raise   # a problem that repeating cannot fix: stop right away
            except StepFailed as err:
                failures += 1
                if failures >= MAX_FAILURES:
                    raise
                self.log(f"{err} Trying again ({failures}/{MAX_FAILURES - 1})...", "WARN")
                self.sleep(2.0)

    # ----- the job itself -----
    def _run(self):
        self._logbook = logbook.LogFile()   # a new log for every run
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
            self._save_log()
            self.set_action(actions.IDLE)
            self.on_done()

    def _pending_accounts(self):
        """The checked accounts that still have something to do today, in list order."""
        queue = accounts.enabled(settings.load())
        if not queue:
            raise StepFailed("No account is checked. Open ACCOUNTS and tick at least one.")
        pending = []
        for acc in queue:
            if progress.is_complete(acc.name):
                self.log(f"{acc.name}: all daily activities are already done today. Skipped.")
            else:
                pending.append(acc)
        return queue, pending

    def _workflow(self):
        queue, pending = self._pending_accounts()
        if not pending:
            self.log("Every checked account has finished its daily activities today. Nothing to do.", "OK")
            return
        self.log(f"Accounts to automate: {len(pending)} of {len(queue)} checked.")
        if goals.game_window() is not None:
            self._close_game("The game is already open. Closing it before starting...")
        count = winutil.minimize_all(skip_pid=os.getpid())
        self.log(f"Minimized {count} window(s).")
        launcher.open_and_arrange(self, self.launcher_path)
        for number, acc in enumerate(pending, 1):
            self.log(f"Account {number} of {len(pending)}: {acc.name}")
            self.pursue(goals.LoginGoal(acc.name, acc.password))
            daily = daily_goals.DailyState.load(acc.name)
            if daily.peer_arena:
                self.log("Peer Arena was already done today. Skipped.")
            else:
                self.pursue(daily_goals.PeerArenaGoal(daily))
            if daily.guild:
                self.log("Guild Dailies were already done today. Skipped.")
            else:
                self.pursue(daily_goals.GuildGoal(daily))
            if daily.quest_board:
                self.log("Quest Board was already done today. Skipped.")
            else:
                self.pursue(daily_goals.QuestBoardGoal(daily))
            # The next goals (mails, events, Monster Extermination) go here.
            if number < len(pending):
                self._close_game("Closing the game for the next account...")
        self.log("All accounts finished the current automations. "
                 "(Mails, events and Monster Extermination are not built yet.)", "OK")

    def _close_game(self, message):
        """Closes the game. It is asked to close first, like the window's close button;
        if it ignores that, its process is ended."""
        hwnd = goals.game_window()
        if hwnd is None:
            return
        self.log(message)
        winutil.close_window(hwnd)
        if not self.wait_until(lambda: goals.game_window() is None, CLOSE_WAIT, 1.0):
            hwnd = goals.game_window()
            if hwnd is not None:
                self.log("The game did not close by itself. Ending its process...", "WARN")
                winutil.kill_process(hwnd)
            if not self.wait_until(lambda: goals.game_window() is None, 15, 1.0):
                raise StepFailed("The game did not close. Close it manually, then press START again.")
        self.sleep(2.0)