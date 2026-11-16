"""Exceptions used to control the flow of the automation."""


class Stopped(Exception):
    """Raised inside the automation when the user presses STOP."""


class StepFailed(Exception):
    """A step could not be completed. The message is shown to the user in the log."""