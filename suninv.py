
from pymodbus.client.sync import *
from pymodbus.register_read_message import ReadHoldingRegistersResponse
from pymodbus.register_read_message import ReadInputRegistersResponse
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.compat import iteritems
from pymodbus.exceptions import ModbusIOException

import logging
import time


class modbusHandler(object):
    minTimeout = 0.1
    def __init__(self, modbus):        
        self.modbus = modbus
        self.latency = modbus.timeout
        self.extendedn = False       

    def updateLatency(self,latency):
        if(latency > 0): 
            if latency > self.latency:
                self.latency = 0.25 * self.latency + 0.75 * latency
            else:
                self.latency = 0.75 * self.latency + 0.25 * latency
            
            self.modbus.timeout = max(self.minTimeout, self.latency * 2) 

    def readInputRegs(self, start, len, unit):
        now = time.time()
        request = self.modbus.read_input_registers(start, len, unit=unit)        
        latency = time.time() - now
        logging.debug("Read values, latency :%.4f",latency)
        if not isinstance(request, ReadInputRegistersResponse):
            logging.error('Error reading values: %s', request)
            raise Exception(request)

        self.updateLatency(latency)
           
        return request.registers

    def readHoldingRegs(self, start, len, unit):
        now = time.time()
        request = self.modbus.read_holding_registers(start, len, unit=unit)
        latency = time.time() - now
        if not isinstance(request, ReadHoldingRegistersResponse):
            logging.error('Error reading info values: %s', request)
            raise Exception(request)

        self.updateLatency(latency)
           
        return request.registers
    
    def writeMultipleRegs(self,start,value,unit):
        now = time.time()
        reply = self.modbus.write_registers(start,value,unit=unit)        
        latency = time.time() - now
        if isinstance(reply, ModbusIOException):
            logging.error('Error writing values: %s', reply)
            raise Exception(reply)

        self.updateLatency(latency)


class SUNINV(object):
    POWERREGISTER = 40

    def __init__(self, modbus, address):
        self.modbus = modbusHandler(modbus)
        self.address = [0]*10
        self.unitCount = 0

    def checkEquipment(self):
        self.unitCount = 0
        for addr in range(1, 4):
            try:
                data = self.modbus.readHoldingRegs(0x0000, 1, unit=addr)
                decoder = BinaryPayloadDecoder.fromRegisters(
                    data, byteorder=Endian.Big, wordorder=Endian.Little)
                result = decoder.decode_16bit_uint()
                if result == 2:
                    self.address[self.unitCount] = addr
                    self.unitCount += 1
                    logging.debug("Found device at %d" % addr)
            except Exception as e:
                logging.debug("No device at %d" % addr)
        return True if (self.unitCount > 0) else False

    def setPowerPercent(self, newValue):
        newValue = int(newValue/self.unitCount)
        for add in range(self.unitCount):
            self.modbus.writeMultipleRegs(
                self.POWERREGISTER, [newValue], self.address[add])
