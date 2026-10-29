"""The failure the CLI reports as a message rather than a traceback."""


class ZepDevError(Exception):
    """A condition the user can act on: refused input, missing prerequisite, bad state.

    Validation keeps raising ValueError. Unexpected tool output keeps raising
    RuntimeError, because a traceback is the right report for a bug.
    """
