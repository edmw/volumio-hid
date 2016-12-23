# coding: utf-8

#
# HID.py
# Reads input events from USB Human interface devices (HID), for example a RFID reader,
# and attempts to send associated control commands to Volumio.
#
# The MIT License
#
# Copyright (c) 2016 Michael Baumgärtner
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import sys, os, logging, asyncio, threading

import contextlib
from functools import partial
from functools import reduce
from operator import add

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

#
# Reads the configuration from file
#
def read_configuration(name):
    import yaml
    return yaml.load(open(os.path.join(__location__, '{}.conf'.format(name)), 'r'))

config = read_configuration('HID')

#
# Gets a value from the configuration for the specified keys.
# If there is no value returns either None or the specified default.
#
def parameter(*keys, default=None):
    def get(dictionary, *keys):
        sentry = object()
        def getter(dictionary, key):
            return dictionary.get(key, sentry) if isinstance(dictionary, dict) else default
        value = reduce(getter, keys, dictionary)
        return value if not value is sentry else default
    return get(config, *keys)

#
# Creates a logger which writes its messages to the syslog
# and additionally to stdout if this script is attached to a terminal.
#
def get_logger(level):
    import logging.handlers
    logger = logging.getLogger('VOLUMIO-HID')
    logger.setLevel(level)
    formatter = logging.Formatter(parameter('logging', 'format'))
    import syslog
    handler = logging.handlers.SysLogHandler('/dev/log', facility=syslog.LOG_LOCAL0)
    handler.formatter = formatter
    logger.addHandler(handler)
    if sys.stdout.isatty():
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    return logger

logger = get_logger(parameter('logging', 'level'))

#
# VOLUMIO
#

volumioIO = None
volumioThread = None
volumioState = {}

from socketIO_client import SocketIO, WebsocketTransport, BaseNamespace, LoggingNamespace
from socketIO_client.exceptions import ConnectionError

@contextlib.contextmanager
def Volumio(server, port):
    global volumioIO
    global volumioThread

    class VolumioNamespace(LoggingNamespace):
        def on_pushState(self, state):
            logger.debug("Received event 'pushState' from Volumio")
            global volumioState
            volumioState = state
        def on_event(self, event, *args):
            logger.debug("Received event '%s' from Volumio (unhandled)", event)

    logger.debug("[Volumio] Connect to '%s:%d'", server, port)
    volumioIO = SocketIO(server, port, VolumioNamespace, wait_for_connection=False)
    volumioThread = threading.Thread(target=volumioIO.wait)
    volumioThread.start()
    try:
        yield volumioIO
    finally:
        logger.debug("[Volumio] Disconnect from '%s:%d'", server, port)
        volumioIO.disconnect()
        volumioIO = None
        volumioThread.join()
        volumioThread = None

#
# Calls Volumio and emits the specified events.
# @param events: List of events. Each event is a tuple of name, data and optional callback.
#
def volumio_emit(events):
    if not volumioIO: return

    if events:
        for event in events:
            parameters = dict(zip(('name', 'data', 'callback'), event))
            event_name = parameters.get('name')
            if event:
                logger.info("Emitting event '%s' to Volumio", event_name)
                event_data = parameters.get('data')
                if event_data:
                    volumioIO.emit(event_name, event_data, callback=parameters.get('callback'))
                else:
                    volumioIO.emit(event_name, callback=parameters.get('callback'))

    else:
        logger.warn("No events specified for Volumio")

#
# VOLUMIO COMMANDS
#

volumioCommands = {}

def volumio_command(func):
    global volumioCommands; volumioCommands[func.__name__] = func
    return func

#
# Calls the specified command on Volumio with the specified arguments.
# @param name Name of the command to execute.
#
def volumio(command_name, *args):
    command = volumioCommands.get(command_name)
    if command:
        command(*args)
    else:
        raise NotImplementedError("Command '{}' not implemented for Volumio".format(command_name))

#
# Calls Volumio to start playing.
#
@volumio_command
def playbackPlay():
    volumio_emit([('play', {})])
#
# Calls Volumio to stop playing.
#
@volumio_command
def playbackStop():
    volumio_emit([('stop', {})])
#
# Calls Volumio play previous title.
#
@volumio_command
def playbackPrevious():
    volumio_emit([('prev', {})])
#
# Calls Volumio to play next title.
#
@volumio_command
def playbackNext():
    volumio_emit([('next', {})])
#
# Calls Volumio to turn volume up.
#
@volumio_command
def volumeUp():
    volumio_emit([('volume', '+')])
#
# Calls Volumio to turn volume down.
#
@volumio_command
def volumeDown():
    volumio_emit([('volume', '-')])
#
# Calls Volumio to toggle mute.
#
@volumio_command
def muteToggle():
    if volumioState.get('mute'):
        volumio_emit([('unmute', {})])
    else:
        volumio_emit([('mute', {})])
#
# Calls Volumio to start playing the specified playlist.
#
@volumio_command
def playPlaylist(name):

    def on_play(*args):
        logger.info("Started playing playlist with result: %s", str(args))

    if name:
        logger.info("Start playing playlist '%s'", name)
        volumio_emit([
            ('stop', {}),
            ('playPlaylist', {"name": name}, on_play),
        ])
    else:
        logger.warn("No playlist name specified to play")
#
# Calls Volumio to shutdown.
#
@volumio_command
def volumioShutdown():
    volumio_emit([('shutdown', {})])

#
# HID
#

from evdev import InputDevice, ecodes, categorize

def grab(label, dev):
    logger.debug("[%s] Get HID device at '%s'", label, dev)
    device = InputDevice(dev)
    logger.debug("[%s] Grab HID device '%s'", label, device.name)
    device.grab()
    return device

def ungrab(label, device):
    logger.debug("[%s] Ungrab HID device '%s'", label, device.name)
    device.ungrab()

#
# Reads input events from RFID HID
#

def rfid(event_loop):

    characters = {
        ecodes.KEY_0: "0",
        ecodes.KEY_1: "1",
        ecodes.KEY_2: "2",
        ecodes.KEY_3: "3",
        ecodes.KEY_4: "4",
        ecodes.KEY_5: "5",
        ecodes.KEY_6: "6",
        ecodes.KEY_7: "7",
        ecodes.KEY_8: "8",
        ecodes.KEY_9: "9",
    }

    command_serial_map =  parameter('rfid', 'serials', default={})

    try:
        hid = grab('RFID', parameter('rfid', 'device'))

        def enter(chars):
            if not chars or len(chars) == 0: return

            serial = reduce(add, chars)
            if serial in command_serial_map:
                command = command_serial_map.get(serial)
                volumio(command)
            elif serial and len(serial) == 10 and serial.isdigit():
                volumio('playPlaylist', serial)

        def read_events(hid):
            chars = []
            while True:
                events = yield from hid.async_read()
                for event in events:
                    if event.type == ecodes.EV_KEY:
                        key = categorize(event)
                        if key.keystate == key.key_down:
                            if key.scancode == ecodes.KEY_ENTER:
                                enter(chars)
                                chars = []
                            else:
                                char = characters.get(key.scancode, '�')
                                chars.append(char)

        def read_events_done(task, device):
            ungrab('RFID', device)

        task = asyncio.async(read_events(hid))
        task.add_done_callback(partial(read_events_done, device=hid))
        return task

    except OSError as x:
        logger.error(x)

#
# MAIN
# Opens a websocket connection to Volumio and
# starts reading events from input devices
# using asynchrouns IO.
#

def supervisor(loop, *tasks, cancel=False, close=False):
    from concurrent.futures import CancelledError

    tasks = list(filter(None, tasks))
    try:
        if cancel:
            for task in tasks:
                task.cancel()
        if len(tasks) == 1:
            future = tasks[0]
        elif len(tasks) > 1:
            future = asyncio.gather(tasks, return_exceptions=True)
        else:
            future = None
        if future:
            while True:
                loop.run_until_complete(future)
    except CancelledError:
        pass
    if close:
        loop.close()

if __name__ == "__main__":
    # asynchronous input loop
    loop = asyncio.get_event_loop()
    task_rfid = None
    try:
        # connect to volumio using websocket
        server = parameter('volumio', 'server', default='localhost')
        port = parameter('volumio', 'port', default='3000')
        with Volumio(server, port) as socket:
            # schedule reading input events from rfid hid
            task_rfid = rfid(loop)
            # start reading input events asynchronously
            logger.info("Clearance ...")
            supervisor(loop, task_rfid)
    except ConnectionError as x:
        logger.error("{}".format(x))
    except KeyboardInterrupt:
        pass
    # stop reading input events asynchronously
    logger.info("Grounding ...")
    supervisor(loop, task_rfid, cancel=True, close=True)
