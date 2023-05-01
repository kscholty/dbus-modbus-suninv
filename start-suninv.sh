#!/bin/bash
#
# Start script for BMV vedirect
#       First parameter: tty device to use
#
# Keep this script running with daemon tools. If it exits because the
# connection crashes, or whatever, daemon tools will start a new one.
#

. /opt/victronenergy/serial-starter/run-service.sh

app="python /opt/victronenergy/dbus-modbus-suninv/dbus-modbus-suninv.py"

start -s /dev/$tty
