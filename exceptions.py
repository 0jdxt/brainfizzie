import time
import click
from click import ClickException, echo


class BrainfuckException(ClickException):
    def __init__(self, msg: str) -> None:
        name = self.__class__.__name__.replace("Exception", "").upper()
        self.message = f"\nBRAINFUCK {name}: " + msg

    def show(self):
        echo(self.message)


class TimeoutException(BrainfuckException):
    def __init__(self, seconds: float) -> None:
        msg = f"program timed out after {seconds or 0:.3f} second(s)"
        super().__init__(msg)


class TerminatedException(BrainfuckException):
    def __init__(self, start: float) -> None:
        msg = f"ctrl-c detected after {time.time()-start:.3f} seconds"
        super().__init__(msg)


class BracketsException(BrainfuckException):
    def __init__(self, bkt: str) -> None:
        self.message = f"BRAINFUCK BRACKETS: missing '{bkt}'"


class InputExcpetion(BrainfuckException):
    def __init__(self) -> None:
        msg = "- specified but no stdin"
        super().__init__(msg)

