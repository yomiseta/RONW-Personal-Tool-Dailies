"""Exceptions used to control the flow of the automation."""


class Stopped(Exception):
    """Raised inside the automation when the user presses STOP."""


class StepFailed(Exception):
    """A step could not be completed. The message is shown to the user in the log."""


class Halt(StepFailed):
    """A step could not be completed and trying again would not help. The bot stops right away
    so the problem can be looked at, instead of repeating the step."""