#!/usr/bin/env python3.7
import logging
import re
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

import click

from utils import (
    brackets_match,
    clean_code,
    State,
    is_copy,
    is_multi,
    get_copy,
    get_multi,
    Timeout,
)
from exceptions import TimeoutException, TerminatedException, InputExcpetion

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter()
ch.setFormatter(formatter)
logger.addHandler(ch)

mem = bytearray(30000)
ptr = 0


def command(char: str, arg: Any = None) -> None:
    global mem
    global ptr

    # - execute command char with args arg
    # - all operations are on current cell i.e. mem[ptr]
    # - as specified by brainfuck, inc and dec ops on cell bytes are
    #   cyclic

    out = f"{char} {arg} -> "

    # pointer right
    # currently limits tape length, could be dynamically enlargened
    if char == ">":
        ptr += arg or 1
        ptr %= len(mem)
        out += str(ptr)

    # pointer left, can't go left of 0
    elif char == "<":
        ptr -= arg or 1
        if ptr < 0:
            ptr = 0
        out += str(ptr)

    # increment by (arg OR 1)
    elif char == "+":
        mem[ptr] = (mem[ptr] + (arg or 1)) % 0x100
        out += f"  {mem[ptr]} {bytes([mem[ptr]])}"

    # decrement by (arg OR 1)
    elif char == "-":
        mem[ptr] = (mem[ptr] - (arg or 1)) % 0x100
        out += f"  {mem[ptr]} {bytes([mem[ptr]])}"

    # print cell byte as ASCII char
    elif char == ".":
        ch = chr(mem[ptr])

        if ch == "$":
            ch = "\n"

        # If no stdout redirect > unbuffered io write/flush
        # else > buffered io print
        # if sys.stdout.isatty():
        #     sys.stdout.write(ch)
        # else:
        print(ch, end="")

        out += f"PRINT: {mem[ptr]} {ch}"

    # get single char from user input
    # if EOF encountered > do nothing
    # else > store ASCII code in cell
    elif char == ",":
        sys.stdout.flush()
        if not sys.stdin.isatty():
            x = sys.stdin.read(1)
        else:
            try:
                x = click.getchar()
            except EOFError:
                # EOF from stdin > treat as EOF char
                x = "\x04"

        out += f"INPUT: {x} {ord(x)}"

        if x != "\x04":
            mem[ptr] = ord(x)

    logger.debug(out)


def parse(code: str) -> None:
    global mem
    global ptr

    brackets_match(code)

    loop = State()
    cmd = State()

    for char in code:
        # if counting and encounter a loop > execute curr_cmd
        # should never encounter ] but just in case
        if char in ("[", "]") and cmd.jump:
            command(cmd.data, cmd.count)
            cmd.reset()

        # prioritise loop building to recursively execute loop
        # > if [ or ] use loop_jump and depth to detect start and end of loop
        if char == "[":
            loop.count += 1
            # if start of loop, set loop_jump and skip char processing
            if not loop.jump:
                loop.jump = True
                continue
        elif char == "]":
            loop.count -= 1

        # > detect if end of loop, execute, reset loop and skip char processing
        if loop.jump and loop.count == 0:
            logger.debug(f"loop: {ptr} {mem[ptr]} {loop.data}")

            # detect type of loop to execute optimised versions
            if loop.data in ("-", "+"):
                # [-] or [+] clears the cell
                mem[ptr] = 0

            elif loop.data == "<":
                # scan left
                while mem[ptr]:
                    ptr -= 1

            elif loop.data == ">":
                # scan right
                while mem[ptr]:
                    ptr += 1

            elif is_multi(loop.data):
                val = mem[ptr]
                # multiply
                for i, m in get_multi(loop.data):
                    new = mem[ptr + 1] + val * m
                    mem[ptr + i] = new % 0x100
                # clear
                mem[ptr] = 0

            elif is_copy(loop.data):
                # copy
                val = mem[ptr]
                for i in get_copy(loop.data):
                    new = mem[ptr + i] + val
                    mem[ptr + i] = new % 0x100
                # clear
                mem[ptr] = 0

            else:
                # loop code
                while mem[ptr]:
                    parse(loop.data)

            logger.debug("loop done")
            loop.reset()
            continue

        # > if in loop, add char to loop, skip char processing
        if loop.jump:
            loop.data += char
            continue

        # next count consecutive cmds for optimisation
        # > if countable > process state and skip char processing
        if char in ("+", "-", "<", ">"):
            # if counting
            #   if cmd is the same > add to count
            #   else cmd is new > execute last cmd, set new cmd and cmd_n
            # else > set cmd_jump, new cmd and inc cmd_n
            if cmd.jump:
                if char == cmd.data:
                    cmd.count += 1
                else:
                    command(cmd.data, cmd.count)
                    cmd.data = char
                    cmd.count = 1
            else:
                cmd.jump = True
                cmd.data = char
                cmd.count += 1
            continue

        # > if uncountable cmd and counting, execute last cmd and reset counting
        if cmd.jump:
            command(cmd.data, cmd.count)
            cmd.reset()

        # execute uncountable command
        command(char)

    # if last cmd is countable > execute
    if cmd.jump:
        command(cmd.data, cmd.count)
        cmd.reset()


timeout_help = """
number (seconds) default=60\nTime after which to kill the program, in seconds. 0 runs the program until completion.

NB:
- SOME PROGRAMS DO NOT COMPLETE AND MAY NEED CTRL-C TO STOP

- SOME PROGRAMS DO NOT STOP AT ALL UNTIL YOU KILL THE TERMINAL"""


@click.command()
@click.argument("code_or_file", type=click.Path(allow_dash=True))
@click.option("--timeout", "-t", default=60, type=click.FLOAT, help=timeout_help)
def main(code_or_file, timeout):
    """Input a string of code directly or the name of a brainfuck file.
    Brainfuck extensions .b and .bf are optional.
    ! NB:
    IF CODE_OR_FILENAME GIVEN AS WELL AS STDIN, STDIN WILL BE TREATED AS PROGRAM INPUT"""

    # if - , check stdin is given
    if code_or_file == "-":
        if sys.stdin.isatty():
            raise InputException(code_or_file)
        code = sys.stdin.read()
    else:
        # if file exists > set fname
        # else - if .bf or .b variants exists > set fname
        #        else > set code
        # prioritise .bf over .b
        p = Path(code_or_file)
        if p.exists():
            fname = p
        else:
            bf = p.with_suffix(".bf")
            bfe = bf.exists()
            b = p.with_suffix(".b")
            be = b.exists()

            if bfe or be:
                fname = bf if bfe else b
            else:
                code = code_or_file

    # try > set code to fname contents
    # exc Name (fname not set) > pass (code is set)
    try:
        with open(fname, "r") as f:
            code = f.read()
    except NameError:
        pass

    logger.debug(clean_code(code))
    start = time.time()
    with Timeout(timeout or None):
        try:
            parse(clean_code(code))
        except KeyboardInterrupt:
            raise TerminatedException(start)
    logger.debug(mem[:20])


if __name__ == "__main__":
    main()

