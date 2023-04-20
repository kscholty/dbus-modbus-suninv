# dbus-modbus-suninv

This is a very special driver. It's used to start an auxiliary inverter if the power of the Multiplus II GX reaches its limit.
It then tries to keep the power at ~2000W by controlling the auxiliary inverter.
The aux.Inv is usually switched off, only if the threshold is reached, it is switched on via a shelly+ 1PM.
