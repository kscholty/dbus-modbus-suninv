#!/usr/bin/python
from argparse import ArgumentParser
import traceback
import serial
import dbus
import dbus.mainloop.glib
import faulthandler
import os
from pymodbus.client.sync import *
import time
import signal
from gi.repository import GLib

import logging
import sys

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext/velib_python'))
from vedbus import VeDbusService, VeDbusItemImport
from suninv import SUNINV
import watchdog
from settingsdevice import SettingsDevice
from shelly import ShellySwitch

log = logging.getLogger()

PROCESS_VERSION='0.1'


class DbusSunInvService:
    MPIINAME = "com.victronenergy.vebus.ttyS3"
    #MPIINAME = "com.victronenergy.system"
    POWERPATH="/Ac/ActiveIn/L1/P" 
    #POWERPATH="/Ac/ActiveIn/L1/Power"
    SHELLYNAME = "shellyplus1pm-44179399f1e0.home.lan"
    
    SETPOINT = -1950
    THRESHOLD = 50
    MAXPOWER = 900
    MODE2DELAY = 240   #4 minutes above SETPOINT in order to switch on the Inverters
    MODE5DELAY = 60*15 #15 Minutes below SETPOINT in order to switch off the Inverters
    MODE3DELAY = 30    #30 secondes before we start regulating

    def __init__(self, tty, address):
        self.devname = os.path.basename(tty)
        self.address = address
        self.modbus = self.makeModbus()
        self.suninv = SUNINV(self.modbus,self.address)
        self.shelly = ShellySwitch(self.SHELLYNAME)    
        self.state = 0
        self.delayStart = 0       
        self._dbus = None
        self.settings = None
        
        #Switch on inverter to ensure that we can detect them...
        self.shelly.switchRelay(True)
        time.sleep(2)

        
        self.dbusconn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
        hasVEBus = self.MPIINAME in self.dbusconn.list_names() 

        if not hasVEBus or not self._detectDevice():
            log.info('No SUNINV detected on %s' % self.devname)
            self.destroy()
            sys.exit(1)

        

        self._initSettings()
        self.watchdog = watchdog.Watchdog()
        self._errorMessage = ''
        self._disconnect = 0
        
        self._readConfig()
        self._initValues()

        self._dbus = VeDbusService("com.victronenergy.suninv-%s" % (self.devname), self.dbusconn)        
        
        self._initDevice()
        self._MPIIPower = VeDbusItemImport(self.dbusconn,self.MPIINAME, self.POWERPATH,createsignal=False)
        self.lastUpdate = time.time()
        self.updateValues()
        self._switchState(5)
        GLib.timeout_add(4000, self._update)
        self.watchdog.start()


    def destroy(self):
        if self._dbus:
            self._dbus.__del__()
            self._dbus = None
        if self.settings:
            self.settings._settings = None
            self.settings = None        


    def _switchOffInverters(self):
        #Switch Inverters off.
        try:
            self.suninv.setPowerPercent(0)
            time.sleep(2)
            self.shelly.switchRelay(False)
        except:
            pass
        
    def _readConfig(self):
        var = self.settings['deviceInstance'].split(':')
        self.role = var[0]
        self.instance = int(var[1])
        pass


    def _initValues(self):        
        self.lastUpdate = time.time()
        self.lastPower = 0
        self.IsInverterOn = 0
        self.powerSetting = 0


    def _initSettings(self):

        settings_path = '/Settings/suninv/%d' % self.address
        SETTINGS = {                   
        }        

        log.info('Waiting for localsettings')
        self.settings = SettingsDevice(self.dbusconn, SETTINGS,
                                       self.settingsChanged, timeout=10)

        """ Add instance path to get our instance"""
        deviceClass = 'com.victronenergy.dcload' 
        path = '/Settings/Devices/suninv_%d' % self.address
        addSettings = {
            'deviceInstance': [path+'/ClassAndVrmInstance', '%s:%d'% (deviceClass, self.address), 0, 0],
            'CustomName': [path+'/CustomName', '', 0, 0],
        }
        self.settings.addSettings(addSettings)

    def customname_changed(self, path, val):
        self.settings['CustomName'] = val
        return True

    def _initDevice(self):               

        self._dbus.add_mandatory_paths(__file__, PROCESS_VERSION, self._connection(),
			self.instance, 0x3e8, 'SUNINV', 0, 0, 1)

        self._dbus.add_path('/Ac/PowerSetting', 0)
        self._dbus.add_path('/Ac/ExtPower', 0)
        
        self._dbus.add_path('/State', self.state)        
        self._dbus.add_path('/Device/Type', "SUN GTIL Inverter")        
        self._dbus.add_path('/ErrorCode', 0, gettextcallback=self._get_text)
        self._dbus.add_path('/ErrorMessage', "")
        self._dbus.add_path('/CustomName', self.settings['CustomName'],
                           writeable=True,
                           onchangecallback=self.customname_changed)        
        
    def settingsChanged(self, setting, servicename, path, changes=None):
        log.debug("%s: %s, %s"%(setting,servicename,path))
        log.debug(changes)

    def _detectDevice(self):        
        success = False
                
        try:                        
            success = self.suninv.checkEquipment()  
                          
        except Exception as e:
            log.error('Exeption while detecting device: %s' % e)   
        
        return (success)   

    def _get_text(self, path, value):
        shortPath = os.path.basename(path)        
        if shortPath == "ErrorCode": return self._errorMessage
        else: return ("%F" % (float(value)))

    def _connection(self):
        return 'Modbus %s %s:%d' % (self.modbus.method.upper(),
                                    os.path.basename(self.modbus.port),
                                    self.address)

    def makeModbus(self):

        dev = '/dev/%s' % self.devname

        log.debug("Device: %s" %dev)
        client = ModbusSerialClient(method='rtu', port=dev, stopbits=serial.STOPBITS_ONE,baudrate=9600, parity=serial.PARITY_NONE)
        if not client.connect():            
            raise Exception('Connection failed to: %s', dev)

        return client    


    def MPIIPowerChanged(self,item,path,changes):
        log.debug("%s changed to : %d"%(path,changes['Value']))



#State Machine:
#    0: Initializing
#    1: Inverters Off, below threshold
#    2: Inverters Off, delay before switch on 
#    3: Inverters On, no regulation  (delay period, 20 sec)
#    4: Inverters On, regulating
#    5: Inverters On,  waiting for switch off, below threshold

    def _switchState(self,newState):
        log.debug("Swithing to state %d" % newState)
        if newState == 0:
            pass
        elif newState == 1:
            if self.state >= 3: self.shelly.switchRelay(False)
        elif newState == 2:
            self.delayStart = time.time()
        elif newState == 3:
            self.shelly.switchRelay(True)
            self.delayStart = time.time()            
        elif newState == 4:
            pass
        elif newState == 5:
            self.suninv.setPowerPercent(0)
            self.delayStart = time.time()
                
        self.state = newState
        self._dbus['/State'] = self.state


    def _checkStateChange(self):
        if self.state == 0:
            #Nothing
            pass
        elif self.state == 1:
            if(self.powerSetting > self.THRESHOLD):
                self._switchState(2)
            pass
        elif self.state == 2:
            if(self.powerSetting == 0):
                self._switchState(1)
            elif time.time() - self.delayStart > self.MODE2DELAY:
                self._switchState(3)            
        elif self.state == 3:              
            if time.time() - self.delayStart > self.MODE3DELAY:
                self._switchState(4)     
        elif self.state == 4:
            if(self.powerSetting == 0):
                self._switchState(5)                 
        elif self.state == 5:       
            if(self.powerSetting > 0):
                self._switchState(4)
            elif  time.time() - self.delayStart > self.MODE5DELAY:
                self._switchState(1)
            
    

    def updateValues(self):
        now = time.time()
        self._MPIIPower._refreshcachedvalue()
        try:
            self.lastPower = self._MPIIPower.get_value()
            if self.lastPower < 0:
                diff = self.SETPOINT - self.lastPower
                newSetting = self.powerSetting + (diff / 2)
                if newSetting < 0:
                    newSetting = 0
                elif newSetting > self.MAXPOWER:
                    newSetting = self.MAXPOWER
                if abs(newSetting - self.powerSetting) > self.THRESHOLD or (newSetting != self.powerSetting and (newSetting == 0 or newSetting == self.MAXPOWER)) or (now-self.lastUpdate > 30):
                    if self.state == 4: self.suninv.setPowerPercent(newSetting) #send value only if in regulation mode
                    self.powerSetting = newSetting
                    self.lastUpdate = now
                    log.debug("Sending %d to Inverter\n" % newSetting)
                else:
                    log.debug("No Update needed. L1: %d current setting is %d, new is %d\n" % (self.lastPower,self.powerSetting,newSetting))
                
                self._dbus['/Ac/PowerSetting'] = self.powerSetting
                self._dbus['/Ac/ExtPower'] = self.lastPower
                self._dbus['/ErrorCode'] = 0
                self._dbus['/ErrorMessage'] = ""
                self._dbus['/Connected'] = 1
                self._error_message = ""
                self._disconnect = 0
        except Exception as e:
            log.error(traceback.format_exc())
            log.error("%s error: %s" % (self._connection(), e))
            self._dbus['/ErrorMessage'] = str(e)
            if self._disconnect > 5:
                self._dbus['/ErrorCode'] = 1
            if self._disconnect > 30:
                self._dbus['/Connected'] = 0
                log.error("Lost connection to device. Exiting")
                os._exit(1)
            self._disconnect += 1
            self._errorMessage = str(e)

    def checkTTY(self):
        return os.path.exists('/dev/%s' % self.devname)
        
    def _update(self):
        if self.checkTTY() != True: 
             raise Exception('TTY invalid: /dev/%s', self.devname)
        self.watchdog.update()
        self.updateValues()
        self._checkStateChange()

        return True

def main():
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("-s", "--serial", dest="device", default="/dev/ttyUSB0",
                      help="tty device", metavar="ADDRESS")
    parser.add_option("-a", "--address", dest="address", type="int",
                      help="device address", metavar="ADDRESS", default=1)    
    parser.add_option("-d","--debug", dest="debug", action="store_true", help="set logging level to debug")
    (opts,args) = parser.parse_args()

    logging.basicConfig(level=(logging.DEBUG if opts.debug else logging.INFO))

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(1))
    faulthandler.register(signal.SIGUSR1)

    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    mainloop = GLib.MainLoop()

    DbusSunInvService(tty=opts.device, address=opts.address)

    logging.info("Starting mainloop, responding only on events")

    mainloop.run()

if __name__ == "__main__":
    main()
