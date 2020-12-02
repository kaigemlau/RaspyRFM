# -*- coding: UTF-8 -*-
#!/usr/bin/env python2.7

from raspyrfm import *
import sensors
from sensors import rawsensor
import sys
import time
import threading
import math
import json
from datetime import datetime
import os

nodes = {
	"74": "Flur",
	"c0": "Hof",
        "e0": "Schlafzimmer",
        "f8": "Arbeitszimmer",
        "68": "Wohnzimmer",
        "30": "Musikzimmer",
}

if raspyrfm_test(2, RFM69):
	print("Found RaspyRFM twin")
	rfm = RaspyRFM(2, RFM69) #when using the RaspyRFM twin
elif raspyrfm_test(1, RFM69):
	print("Found RaspyRFM single")
	rfm = RaspyRFM(1, RFM69) #when using a single single 868 MHz RaspyRFM
else:
	print("No RFM69 module found!")
	exit()


try:
	import paho.mqtt.client as mqtt
	mqttClient = mqtt.Client()
        mqttClient.username_pw_set("mqtt", "mqtt")
	mqttClient.connect("localhost", 1883, 60)
	mqttClient.loop_start()
except:
	mqttClient = None
	print("mqtt init error")

rfm.set_params(
    Freq = 868.300, #MHz center frequency
    Datarate = 9.579, #kbit/s baudrate
    ModulationType = rfm69.FSK, #modulation
    Deviation = 30, #kHz frequency deviation OBW = 69.6/77.2 kHz, h = 6.3/3.5
    SyncPattern = [0x2d, 0xd4], #syncword
    Bandwidth = 100, #kHz bandwidth
        #AfcBandwidth = 150,
	#AfcFei = 0x0E,
    RssiThresh = -100, #-100 dB RSSI threshold
)

class BaudChanger(threading.Thread):
	baud = False
	def __init__(self):
		threading.Thread.__init__(self)

	def run(self):
		while True:
			time.sleep(15) 
			if self.baud:
				rfm.set_params(Datarate = 9.579)
			else:
				rfm.set_params(Datarate = 17.241)
			self.baud = not self.baud

baudChanger = BaudChanger()
baudChanger.daemon = True
baudChanger.start()

time.sleep(4)
print "Waiting for sensors..."
cache = {}
while 1:
	rxObj = rfm.receive(7)
        payload = {}
       	try:
		sensorObj = rawsensor.CreateSensor(rxObj)
		sensorData = sensorObj.GetData()
		payload["ID"] = sensorData["ID"]
		T = sensorData["T"][0]
		payload["T"] = T
	except:
		continue
 

        if payload["ID"] not in nodes:
            continue

	payload["RSSI"] = int(rxObj[1])
	payload["afc"] = rxObj[2]
        if(sensorData['batlo'] == True):
            payload["BAT"] = 20
        else:
            payload["BAT"] = 100
	payload["batlo"] = sensorData['batlo']
	payload["init"] = sensorData["init"]
        payload["room"] = nodes[sensorData['ID']]
	if 'RH' in sensorData:
		payload["RH"] = int(sensorData['RH'][0])

	if not payload["ID"] in cache:
		cache[payload["ID"]] = {}
		cache[payload["ID"]]["count"] = 1
                config={}
                config["device_class"]="temperature"
                config["unique_id"]=payload["ID"]+"_T"
                dev={}
                dev["identifiers"]=payload["ID"]
                dev["name"]="Sensor "+payload["room"]
                config["device"]=dev
                config["name"]="Temperatur "+payload["room"]
                config["state_topic"]="home/sensor/"+payload["room"]+"/state"
                config["value_template"]="{{ float(value_json.T) }}"
                config["unit_of_measurement"]=u"\N{DEGREE SIGN}"+"C"
                mqttClient.publish('home/sensor/'+payload["room"]+'T/config',json.dumps(config), retain=True)
                config["device_class"]="humidity"
                config["name"]="Luftfeuchte "+payload["room"]
                config["value_template"]="{{ value_json.RH }}"
                config["unit_of_measurement"]="%"
                config["unique_id"]=payload["ID"]+"_RH"
                mqttClient.publish('home/sensor/'+payload["room"]+'RH/config',json.dumps(config), retain=True)
                config["device_class"]="signal_strength"
                config["name"]="Signal "+payload["room"]
                config["value_template"]="{{ value_json.RSSI }}" 
                config["unique_id"]=payload["ID"]+"_RSSI"
                config["unit_of_measurement"]="dBm"
                mqttClient.publish('home/sensor/'+payload["room"]+'RSSI/config',json.dumps(config), retain=True)
                config["device_class"]="battery"
                config["name"]="Battery "+payload["room"]
                config["value_template"]="{{ value_json.BAT }}"
                config["unique_id"]=payload["ID"]+"_BAT"
                config["unit_of_measurement"]="%"
                mqttClient.publish('home/sensor/'+payload["room"]+"BAT/config",json.dumps(config), retain=True)

        ID=payload["ID"]
        update=False
        if cache[ID]["count"] == 1: 
                update=True
        elif cache[ID]["payload"]["T"] != payload["T"]:
                update=True
        elif 'RH' in sensorData:
            if cache[ID]["payload"]["RH"] != payload["RH"]:
                update=True
        
        cache[ID]["count"] += 1

        if cache[ID]["count"] > 2:
            if abs(cache[ID]["payload"]["T"] - payload["T"]) > 10:
                update=False
                print(payload)
            elif abs(cache[ID]["payload"]["RH"] - payload["RH"]) > 20:
                update=False
                print(payload)

        if not update:
            continue

	cache[payload["ID"]]["payload"] = payload;
	cache[payload["ID"]]["ts"] = datetime.now();

	try:
		if mqttClient:
			mqttClient.publish('home/sensor/'+ payload['room']+'/state', json.dumps(payload), retain=True)
	except:
		pass
