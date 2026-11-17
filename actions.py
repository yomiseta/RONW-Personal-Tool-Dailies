"""Goal names shown in the ACTION bar. The bot keeps working on the current goal until it is verified done."""

IDLE = "Idle"
MAILS = "Check and read mails"
EVENTS = "Retrieve from Events"
PEER_ARENA = "Peer Arena"
QUEST_BOARD = "Quest Board"
GUILD = "Guild Dailies"


def logging_in(account):
    return f"Logging in {account}"