# coding: utf-8

#
# RFID.py
# Reads input events from a USB RFID reader connected as HID
# and attempts to play an associated playlist with volumio.
#

import sys, logging

#
# Creates a logger which writes its messages to the syslog
# and additionally to stdout if this script is attached to a terminal.
#
def get_logger():
    import logging.handlers
    logger = logging.getLogger('rfid')
    formatter = logging.Formatter('%(name)s: %(message)s')
    handler = logging.handlers.SysLogHandler('/dev/log')
    handler.formatter = formatter
    logger.addHandler(handler)
    if sys.stdout.isatty():
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    return logger

logger = get_logger()
logger.setLevel(logging.DEBUG)

#
# Calls volumio and emits the specified commands.
# @param commands: List of commands. Each command a tuple of function, arguments and optional callback.
#
def volumio(commands):

    from socketIO_client import SocketIO
    from socketIO_client.exceptions import ConnectionError

    if commands:
        logger.info("Start playing playlist '%s'", playlist_name)
        try:
            with SocketIO('localhost', 3000, wait_for_connection=False) as socketIO:
                for command in commands:
                    parameters = dict(zip(('function', 'arguments', 'callback'), command))
                    event = parameters.get('function')
                    if event:
                        data = parameters.get('arguments')
                        if data:
                            socketIO.emit(event, data, callback=parameters.get('callback'))
                        else:
                            socketIO.emit(event, callback=parameters.get('callback'))
        except ConnectionError, x:
            logger.warn("volumio error: {}".format(x))
    else:
        logger.warn("volumio: no commands specified")
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
    volumio([('previous', {})])
#
# Calls volumio to play next title.
#
def playbackNext():
    volumio([('next', {})])
#
# Calls volumio to increase volume.
#
def volumeUp():
    def on_state(*args):
        # FIXME: get volume from result, increase volume, set new volume
        logger.info("%s", str(args))
        volume = 33
        volume = min(100, volume + 10)
        volumio([('volume', {"vol": volume})])
    volumio([('getstate', {}, on_state)])
#
# Calls volumio to decrease volume.
#
def volumeDown():
    def on_state(*args):
        # FIXME: get volume from result, decrease volume, set new volume
        logger.info("%s", str(args))
        volume = 33
        volume = max(0, volume - 10)
        volumio([('volume', {"vol": volume})])
    volumio([('getstate', {}, on_state)])
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
            ('playPlaylist', {"name": playlist_name}, on_play),
        ])
    else:
        logger.warn("playPlaylist: no playlist name specified")

#
# Reads input events from HID
#

if __name__ == "__main__":

    import contextlib

    from operator import add

    from evdev import InputDevice, ecodes, categorize

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
    def HID(dev):
        logging.debug("HID: Get device at '%s'", dev)
        device = InputDevice(dev)
        device.grab()
        try:
            yield device
        except KeyboardInterrupt:
            pass
        finally:
            logging.debug("HID: Ungrab device at '%s'", dev)
            device.ungrab()

    try:
        with HID('/dev/input/by-id/usb-13ba_Barcode_Reader-event-kbd') as hid:

            def enter(chars):
                serial = reduce(add, chars)
                if   serial = '1234567890': playbackPlay()
                elif serial = '1234567890': playbackStop()
                elif serial = '1234567890': playbackPrevious()
                elif serial = '1234567890': playbackNext()
                elif serial = '1234567890': volumeUp()
                elif serial = '1234567890': volumeDown()
                elif serial and len(serial) == 10 and serial.isdigit():
                    playPlaylist(name=serial)

            chars = []
            for event in hid.read_loop():
                if event.type == ecodes.EV_KEY:
                    key = categorize(event)
                    if key.keystate == key.key_down:
                        if key.scancode == ecodes.KEY_ENTER:
                            enter(chars)
                            chars = []
                        else:
                            char = characters.get(key.scancode, '�')
                            chars.append(char)

    except OSError, x:
        logger.error(x)
