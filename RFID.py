# coding: utf-8

#
# RFID.py
# Reads input events from a USB RFID reader connected as HID
# and attempts to play a associated playlist with volumio.
#

import sys, signal, logging

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
logger.setLevel(logging.INFO)

#
# Calls volumio to start playing the specified playlist.
#
def volumio(playlist_name):

    from socketIO_client import SocketIO
    from socketIO_client.exceptions import ConnectionError

    def on_play(*args):
        logger.info("Started playing playlist with result: %s", str(args))

    if playlist_name and len(playlist_name) == 10:
        logger.info("Start playing playlist '%s'", playlist_name)
        try:
            with SocketIO('localhost', 3000, wait_for_connection=False) as socketIO:
                socketIO.emit('stop')
                socketIO.emit('playPlaylist', {"name": playlist_name}, on_play)
        except ConnectionError, x:
            logger.warn(x)

#
# Reads input events from HID
#

if __name__ == "__main__":

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

    try:

        # open HID device for RFID reader
        device = InputDevice('/dev/input/by-id/usb-13ba_Barcode_Reader-event-kbd')

        # signal handling
        def signal_handler(signal, frame):
            device.ungrab()
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)

        # grab device exclusivly
        device.grab()

        def enter(chars):
            serial = reduce(add, chars)
            volumio(playlist_name=serial)

        chars = []
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                if key.keystate == key.key_down:
                    if key.scancode == ecodes.KEY_ENTER:
                        enter(chars)
                        chars = []
                    else:
                        char = characters.get(key.scancode)
                        if char:
                            chars.append(char)

    except OSError, x:
        logger.error(x)


