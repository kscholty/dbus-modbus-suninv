
import logging
import requests

class ShellySwitch:
    SWITCHCOMMAND ='/rpc/Switch.set?id=0&on=%s'
    STATUSCOMMAND ='/rpc/Switch.GetStatus?id=0'
    BASECOMMAND = '/Shelly'
    def __init__(self,name):
        self.name = name

    def _getShellyData(self, isBase):
       URL = self._getShellyStatusUrl() if not isBase else self._getShellyBaseUrl() 
       meter_r = requests.get(url = URL)
    
    # check for response
       if not meter_r:
           raise ConnectionError("No response from Shelly 1PM - %s" % (URL))
    
       meter_data = meter_r.json()     
    
    # check for Json
       if not meter_data:
           raise ValueError("Converting response to JSON failed")
   
       return meter_data
     
    def switchRelay(self,on):
        command = self.SWITCHCOMMAND % ('true' if on else 'false')
        URL = "http://%s%s" % (self.name,command)
        answer = requests.get(url = URL)
        if not answer:
           raise ConnectionError("No response from Shelly 1PM - %s" % (URL))

    def _getStatusUrl(self):        
        URL = "http://%s%s" % (self.name,self.STATUSCOMMAND)
        return URL
    
    def _getBaseUrl(self):
        URL = "http://%s%s" % (self.name,self.BASECOMMAND)
        return URL

    

