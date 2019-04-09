from typing import Iterator, List, Optional, Tuple
import re
import signal

from exceptions import TimeoutException, BracketsException


def brackets_match(code: str) -> None:
    tot = 0
    for char in re.sub(r"[^\[\]]", "", code):
        if char == "[":
            tot += 1
        elif char == "]":
            tot -= 1

    # tot > 0 -> missing ]
    # tot < 0 -> missing [
    bkt = ("[", "]")[tot > 0]

    if tot:
        raise BracketsException(bkt)


def clean_code(code: str) -> str:
    return re.sub(r"[^<>+-.,\[\]]", "", code)


class State:
    def __init__(self) -> None:
        self.jump = False
        self.data = ""
        self.count = 0

    reset = __init__


def is_copy(loop) -> bool:
    if len(loop) < 2 or loop[0] != "-":
        return False

    # [-((>)+)(<)]
    # where there can be multiple > in each (>+) group
    # and multiple (>+) groups in the loop
    # total (>) must == total (<)

    parts = loop[1:].split("+")  # ['>']*N + ['<'*N]
    left = "".join(parts[:-1])
    right = parts[-1]
    return (
        len(left) == len(right)
        # non copy loops will have extra chars
        and len(left) * ">" == left
        and len(right) * "<" == right
    )


def get_copy(loop: str) -> Iterator[int]:
    # ['>'*N_i] + ['<'*N]
    parts = loop[1:].split("+")
    left = parts[:-1]

    # length of split group is N_i
    # cumulatively sum N_i to get offsets
    cs: List[int] = []
    for g in left:
        cs.append(sum(cs) + len(g))
        yield cs[-1]


def is_multi(loop: str) -> bool:

    # [-((>)(+))(<)]
    # similar to copy loops but also allows
    # multiple + in any of the (>+) groups

    # works since is_copy assumes single + in (>+) groups
    if not is_copy(loop):
        return False

    # differentiate from copy by checking for any (>+) groups with multiple +
    # > ['']*N_i + ['+'*M_i] + ...
    sp_chars = re.sub(r"-", "", loop).split("<")[0].split(">")
    # > check any M_i > 1
    return any(map(lambda x: len(x) > 1, sp_chars))


def get_multi(loop) -> Iterator[Tuple[int, int]]:
    # [-(>+)(<)]
    # red(uced) =  ['']*N_i + ['+'*M_i] + ...
    red = loop[1:].split("<")[0].split(">")[1:]

    # get coefficients (M) by counting + in (>+) groups, removing + groups
    coff = filter(lambda x: x, map(len, red))

    # cumulative sum of (+) group lengths to get offsets (N)
    offs: List[int] = []
    for g in loop[1:].split("+")[:-1]:
        if g:
            offs.append(offs[-1] + len(g) if offs else len(g))

    return zip(offs, coff)


class Timeout:
    def __init__(self, seconds: Optional[float] = None) -> None:
        self.seconds = seconds

    def handle_timeout(self, signum, frame):
        raise TimeoutException(self.seconds)

    def __enter__(self):
        if self.seconds:
            signal.signal(signal.SIGALRM, self.handle_timeout)
            signal.setitimer(signal.ITIMER_REAL, self.seconds)

    def __exit__(self, type, value, traceback):
        if self.seconds:
            signal.alarm(0)
