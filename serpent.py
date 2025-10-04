#!/usr/bin/python3

import argparse
import serial
import sys
from queue import Queue
from time import sleep
import tty
import threading
import termios
import fcntl
import os
import importlib.util
from pathlib import Path


VERSION = "1.0.1"

BACKSPACE = 127

INPUT_FILTER = "serpent_input_filter"
OUTPUT_FILTER = "serpent_output_filter"


class Prompt:
    def __init__(self, echo: bool):
        self.__fd = sys.stdin.fileno()
        self.__old_settings = termios.tcgetattr(self.__fd)

        self.__orig_fl = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, self.__orig_fl | os.O_NONBLOCK)

        tty.setcbreak(sys.stdin)

        self.__echo = echo
        self.__prompt = ""
        self.__output_queue = Queue()
        self.__history = []


    def __del__(self):
        termios.tcsetattr(self.__fd, termios.TCSADRAIN, self.__old_settings)


    def paint(self) -> str:
        """
        Paint the prompt on the terminal and return a line of user input
        if enter has been pressed, otherwise None.
        """

        line_read = None

        c = sys.stdin.buffer.read(1)
        if c:
            if ord(c) == BACKSPACE and len(self.__prompt) >= 1:
                self.__prompt = self.__prompt[:-1]
            elif c == b'\n':
                if self.__echo:
                    self.__output_queue.put("> " + self.__prompt)

                line_read = self.__prompt
                self.__history.append(line_read)
                
                self.__prompt = ""
            elif c == b'\t':
                self.__autocomplete()
            else:
                s = str(c, "ascii")
                if s.isprintable():
                    self.__prompt = self.__prompt + s

        # delete prompt
        print("\r\033[2K", end="", flush=True)

        if self.__output_queue.empty() == False:
            line = self.__output_queue.get_nowait()

            print(line)

        # reprint prompt
        print("\r\033[2K>", self.__prompt, end='', flush=True)
        
        return line_read


    def print(self, line):
        self.__output_queue.put(line)


    def __autocomplete(self) -> str:
        for i in range(len(self.__history) - 1, -1, -1):
            if self.__history[i].startswith(self.__prompt):
                self.__prompt = self.__history[i]


class Serpent:
    def __init__(self, 
                 serial: serial.Serial,
                 input_filter,
                 output_filter,
                 echo: bool,
                 extra_args: dict):
        self.__serial = serial
        self.__input_filter = input_filter
        self.__output_filter = output_filter
        self.__extra_args = extra_args
        self.__stop_event = threading.Event()
        self.__prompt = Prompt(echo)


    def run(self):
        thread = threading.Thread(target=self.__read_serial)
        thread.daemon = True
        thread.start()

        try:
            while True:
                user_input = self.__prompt.paint()
                if user_input:
                    cmd = self.__output_filter(user_input, self.__extra_args)
                    if cmd:
                        self.__serial.write(cmd)
                
                if self.__stop_event.is_set():
                    raise Exception("Connection closed unexpectedly")
                
                sleep(0.01)

        except KeyboardInterrupt:
            print("r\033[2K\nTerminated")
        except Exception as ex:
            print(f"\r\033[2K\n{ex}")


    def __read_serial(self):
        try:
            buffer = bytes()
            while True:
                buffer = buffer + self.__serial.read_all()

                lines, buffer = self.__input_filter(buffer, self.__extra_args)

                for line in lines:
                    self.__prompt.print(line)

                sleep(0.01)
        except:
            self.__stop_event.set()


def __load_plugin(plugin: str) -> tuple:
    path = Path(plugin)
    if not path.exists():
        raise FileNotFoundError(f"Plugin file '{plugin}' does not exist")

    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)

    input_filter = getattr(module, INPUT_FILTER, None)
    output_filter = getattr(module, OUTPUT_FILTER, None)

    if input_filter is None:
        raise Exception(f"Plugin '{plugin}' does not contain '{INPUT_FILTER}'")
    
    if output_filter is None:
        raise Exception(f"Plugin '{plugin}' does not contain '{OUTPUT_FILTER}'")

    return input_filter, output_filter


def __parse_unknown_args(args: list[str]) -> dict:
    extra_args = {}

    for arg in args:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            extra_args[key] = value

    return extra_args


def __get_config(config: str) -> tuple[int, bool, float]:
    b = int(config[0])
    p = config[1]
    s = float(config[2:])

    return (b, p, s)


def __default_text_input_filter(data: bytes, extra_args: dict) -> tuple[list[str], bytes]:
    lines = []

    while b'\n' in data:
        pos = data.find(b'\n')

        line = data[:pos].decode("ascii", errors="ignore")
        lines.append(line)

        data = data[pos + 1:]

    return lines, data


def __default_binary_input_filter(data: bytes, extra_args: dict) -> tuple[list[str], bytes]:
    return [data.hex(), bytes()]


def __default_output_filter(user_input: str, extra_args: dict) -> bytes:
    return (user_input + '\n').encode("ascii")


def __get_default_filters(binary: bool) -> tuple:
    if binary:
        return (__default_binary_input_filter, __default_output_filter)
    else:
        return (__default_text_input_filter, __default_output_filter)


def main() -> int:
    if "--version" in sys.argv:
        print(f"serpent v{VERSION}")
        return 0

    parser = argparse.ArgumentParser(
        description="Serial Command Prompt"
    )
    parser.add_argument(
        "--port", "-p",
        help="Serial port",
        required=True
    )
    parser.add_argument(
        "--baudrate", "-b",
        type=int,
        default=115200,
        help="Baudrate (default: 115200)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="8N1",
        help="Serial configuration (default: 8N1)"
    )
    parser.add_argument(
        "--binary",
        default=False,
        action="store_true",
        help="Process input/output in binary (does not apply to plugin)"
    )
    parser.add_argument(
        "--echo", "-e",
        default=False,
        action="store_true",
        help="Echo back user inputs"
    )
    parser.add_argument(
        "--plugin",
        type=str,
        help=f"Filter plugin (must provide {INPUT_FILTER} and {OUTPUT_FILTER} functions)"
    )

    args, unknown = parser.parse_known_args()

    port = args.port
    baudrate = args.baudrate
    input_filter, output_filter = __load_plugin(args.plugin) if args.plugin is not None else __get_default_filters(args.binary)
    echo = args.echo
    extra_args = __parse_unknown_args(unknown)
    bytesize, parity, stopbits = __get_config(args.config)

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baudrate
    ser.timeout = 1
    ser.dtr = 0
    ser.rts = 0
    ser.bytesize = bytesize
    ser.parity = parity
    ser.stopbits = stopbits

    try:
        ser.open()
    except:
        print(f"Failed to open serial port '{port}'")
        return -1
    
    serpent = Serpent(ser, input_filter, output_filter, echo, extra_args)
    serpent.run()
    
    return 0


if __name__ == "__main__":
    ret = main()
    exit(ret)
