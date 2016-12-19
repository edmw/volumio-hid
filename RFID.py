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
    logger = logging.getLogger()
    formatter = logging.Formatter('%(name)s: %(message)s')
    handler = logging.handlers.SysLogHandler('/dev/log')
    handler.formatter = formatter
    logger.addHandler(handler)
    if sys.stdout.isatty():
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    return logging.getLogger('RFID')

logger = get_logger()
logger.setLevel(logging.INFO)

#logging.getLogger('socketIO-client').setLevel(logging.DEBUG)
#logging.basicConfig()

#
# VOLUMIO
#

volumioIO = None

#
# Calls volumio and emits the specified commands.
# @param commands: List of commands. Each command a tuple of function, arguments and optional callback.
#
def volumio(commands):

    from socketIO_client import SocketIO
    from socketIO_client.exceptions import ConnectionError

    def on_pushState(*args):
        pass

    if commands:
        global volumioIO

        if volumioIO == None:
            try:
                volumioIO = SocketIO('localhost', 3000, wait_for_connection=False)
                volumioIO.on('pushState', on_pushState)
            except ConnectionError, x:
                logger.warn("{}".format(x))
                return

        for command in commands:
            parameters = dict(zip(('function', 'arguments', 'callback'), command))
            event = parameters.get('function')
            if event:
                logger.info("Emitting event '%s' to Volumio.", event)
                data = parameters.get('arguments')
                if data:
                    volumioIO.emit(event, data, callback=parameters.get('callback'))
                else:
                    volumioIO.emit(event, callback=parameters.get('callback'))
                volumioIO.wait_for_callbacks(seconds=0.1)

    else:
        logger.warn("No commands specified for Volumio.")

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
        logger.info("Start playing playlist '%s'.", name)
        volumio([
            ('stop', {}),
            ('playPlaylist', {"name": name}, on_play),
        ])
    else:
        logger.warn("No playlist name specified to play.")

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
        logging.debug("[HID] Get HID device at '%s'.", dev)
        device = InputDevice(dev)
        device.grab()
        try:
            yield device
        except KeyboardInterrupt:
            pass
        finally:
            logging.debug("[HID] Ungrab HID device at '%s'.", dev)
            device.ungrab()

    try:
        with HID('/dev/input/by-id/usb-13ba_Barcode_Reader-event-kbd') as hid:
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

            logger.info("Clearance to start!")

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

