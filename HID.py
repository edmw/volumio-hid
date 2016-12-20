# coding: utf-8

#
# RFID.py
# Reads input events from a USB RFID reader connected as HID
# and attempts to play an associated playlist with volumio.
#

import sys, logging, asyncio

import contextlib

#
# Creates a logger which writes its messages to the syslog
# and additionally to stdout if this script is attached to a terminal.
#
def get_logger(level):
    import logging.handlers
    logger = logging.getLogger()
    logger.setLevel(level)
    formatter = logging.Formatter('%(name)s: %(message)s')
    handler = logging.handlers.SysLogHandler('/dev/log')
    handler.formatter = formatter
    logger.addHandler(handler)
    if sys.stdout.isatty():
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    logger = logging.getLogger('RFID')
    logger.setLevel(level)
    return logger

logger = get_logger(logging.DEBUG)

#logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
#logging.basicConfig()

#
# VOLUMIO
#

volumioIO = None

from socketIO_client import SocketIO
from socketIO_client.exceptions import ConnectionError

@contextlib.contextmanager
def Volumio(server, port):
    global volumioIO

    def on_pushState(*args):
        pass

    logger.debug("[Volumio] Connect to '%s:%d'", server, port)
    volumioIO = SocketIO(server, port, wait_for_connection=False)
    volumioIO.on('pushState', on_pushState)
    try:
        yield volumioIO
    finally:
        logger.debug("[Volumio] Disconnect")
        volumioIO.disconnect()

#
# Calls volumio and emits the specified commands.
# @param commands: List of commands. Each command a tuple of function, arguments and optional callback.
#
def volumio(commands):
    if commands:
        for command in commands:
            parameters = dict(zip(('function', 'arguments', 'callback'), command))
            event = parameters.get('function')
            if event:
                logger.info("Emitting event '%s' to Volumio", event)
                data = parameters.get('arguments')
                if data:
                    volumioIO.emit(event, data, callback=parameters.get('callback'))
                else:
                    volumioIO.emit(event, callback=parameters.get('callback'))

    else:
        logger.warn("No commands specified for Volumio")

#
# Calls volumio to start playing.
#
def playbackPlay():
    volumio([('play', {})])
#
# Calls volumio to stop playing.
#
def playbackStop():
    volumio([('stop', {})])
#
# Calls volumio play previous title.
#
def playbackPrevious():
    volumio([('prev', {})])
#
# Calls volumio to play next title.
#
def playbackNext():
    volumio([('next', {})])
#
# Calls volumio to increase volume.
#
def volumioShutdown():
    volumio([('shutdown', {})])
#
# Calls volumio to start playing the specified playlist.
#
def playPlaylist(name):

    def on_play(*args):
        logger.info("Started playing playlist with result: %s", str(args))

    if name:
        logger.info("Start playing playlist '%s'", name)
        volumio([
            ('stop', {}),
            ('playPlaylist', {"name": name}, on_play),
        ])
    else:
        logger.warn("No playlist name specified to play")

#
# Reads input events from RFID HID
#

from evdev import InputDevice, ecodes, categorize

RFID_DEVICE = '/dev/input/by-id/usb-13ba_Barcode_Reader-event-kbd'
RFID_VENDOR = 0x13ba
RFID_PRODUCT = 0x0018

def rfid(event_loop):

    from operator import add

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

    @contextlib.contextmanager
    def RFID(dev):
        logger.debug("[RFID] Get HID device at '%s'.", dev)
        device = InputDevice(dev)
        device.grab()
        try:
            yield device
        finally:
            logger.debug("[RFID] Ungrab HID device at '%s'.", dev)
            device.ungrab()

    try:
        with RFID(RFID_DEVICE) as hid:

            def enter(chars):
                if not chars or len(chars) == 0: return

                serial = reduce(add, chars)
                if   serial == '0004775724': playbackPlay()
                elif serial == '0004626662': playbackStop()
                elif serial == '0004797126': playbackPrevious()
                elif serial == '0004797218': playbackNext()
                elif serial == '0005156540': volumioShutdown()
                elif serial and len(serial) == 10 and serial.isdigit():
                    playPlaylist(name=serial)

            chars = []

            def read_events(hid):
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

            logger.info("Clearance to start!")

            asyncio.async(read_events(hid))

            try:
                event_loop.run_forever()
            finally:
                event_loop.close()

    except OSError as x:
        logger.error(x)

#
# MAIN
#

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        with Volumio('localhost', 3000) as socket:
            rfid(loop)
            socket.wait()
    except ConnectionError as x:
        logger.error("{}".format(x))
    except KeyboardInterrupt:
        pass
    for task in asyncio.Task.all_tasks():
        task.cancel() 
