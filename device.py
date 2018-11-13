import paho.mqtt.client as mqtt # import the client
from thingsboard import Thingsboard
import time
import threading
import json
import base64
import os
import logging
from parser import parse_alp

logger = logging.getLogger(__name__)

class Device:

    # ------------------------------
    # Broker addresses
    # ------------------------------
    broker_address_lora='eu.thethings.network'
    broker_address_d7='backend.idlab.uantwerpen.be'

    # ------------------------------
    # Load keys
    # ------------------------------
    with open('keys.json') as f:
        keys = json.load(f)

    thingsboard = Thingsboard(keys['thingsboard']['url'], 1883, keys['thingsboard']['access_token'])

    def __init__(self, device_name, device_id):
        self.device_name = device_name
        self.device_id = device_id
        self.queue_d7 = {}
        self.processor = threading.Thread()
        # ------------------------------
        # Subscribe to Dash-7
        # ------------------------------
        try:
            self.client_d7 = mqtt.Client() #create new instance
            self.client_d7.on_message=self.on_message_d7 #attach function to callback
            # self.client_d7.on_connect=self.on_connect
            print('connecting to broker '+self.broker_address_d7)
            self.client_d7.connect(self.broker_address_d7) #connect to broker
            self.client_d7.loop_start()
            print('Subscribing to topic '+'/d7/'+self.device_id+'/#')
            # self.client_d7.subscribe('/d7/#')
            self.client_d7.subscribe('/d7/'+self.device_id+'/#')
        except:
            print('connecting to Dash-7 backend failed')
        # ------------------------------
        # Subscribe to LoRaWAN
        # ------------------------------
        try:
            self.client_lora = mqtt.Client() #create new instance
            self.client_lora.username_pw_set(self.keys['ttn']['app_id'], self.keys['ttn']['access_key'])
            self.client_lora.on_message=self.on_message_lora #attach function to callback
            print('connecting to broker '+self.broker_address_lora)
            self.client_lora.connect(self.broker_address_lora) #connect to broker
            self.client_lora.loop_start()
            print('Subscribing to topic '+'eguard/devices/'+device_name+'/up')
            self.client_lora.subscribe('eguard/devices/'+device_name+'/up')
        except:
            print('connecting to The Things Network failed')

    def __del__(self):
        self.client_d7.loop_stop()
        self.client_lora.loop_stop()

    def on_message_d7(self, client, userdata, message):
        print('--------------- Dash-7 Received ---------------')
        raw = str(message.payload.decode('utf-8'))
        print('message topic: '+str(message.topic))
        hardware_id = message.topic.split('/')[2]
        gateway_id = message.topic.split('/')[3]
        print('hardware_id: '+hardware_id)
        print('message qos: '+str(message.qos))
        print('message retain flag: '+str(message.retain))
        print('raw message: '+raw)
        dict = parse_alp(raw)
        self.queue_d7[gateway_id] = [int(dict['rx_level'])]   # save rx_level for every receiving gateway
        print('queue',self.queue_d7)
        print('thread',self.processor.is_alive())
        if not self.processor.is_alive():
            print('Thread started')
            self.processor = threading.Thread(target=self.process_data_counter, args=[dict['data'], hardware_id])
            print('Thread created')
            self.processor.start()
            print('Thread started')

        # if not self.processor_lock.is_locked():
            # self.processor_lock.acquire()
            # self.processor = threading.Timer(2, target=self.process_data_counter, args=(dict['data'], hardware_id))
            # self.processor_lock = processor.Lock()
            # self.processor.start()
        print('-----------------------------------------------')

    def process_data_counter(self, data, device_id):
        time.sleep(5)
        print('-------------------- Fingerprint --------------------')
        self.process_data(data, device_id)   # process data of first received packet
        print('queue',self.queue_d7)
        # <estimate location code here>
        self.queue_d7 = {}                      # clear queue
        # self.processor.release()                # release processor
        print('-----------------------------------------------')

    def on_message_lora(self, client, userdata, message):
        print('--------------- LoRa Received ---------------')
        self.payload = str(message.payload.decode('utf-8'))
        print('message received: '+self.payload)
        print('message topic: '+str(message.topic))
        print('message qos: '+str(message.qos))
        print('message retain flag: '+str(message.retain))
        self.payload = json.loads(self.payload)
        print('payload: '+str(self.payload))
        self.payload_raw = str(self.payload['payload_raw'])
        print('payload_raw: '+self.payload_raw)

        self.bin = base64.b64decode(str(self.payload_raw))
        print('bin: '+bin)
        self.hex = self.bin.encode('hex')
        print('hex: ',hex)

        self.data = []
        for i in range(8, int(len(self.hex)), 2):   # ignore first 4 bytes (= 8 niples)
            self.data.append(int(self.hex[i:i+2],16)) # convert hex byte to int
        process_data(self.data, self.payload['hardware_serial'])
        print('---------------------------------------------')

    def process_data(self, data, device_id):
        print('data: '+str(data))
        temperature = float((data[1]<<8)|data[0])/100
        humidity = float((data[3]<<8)|data[2])/100
        print('Temperature [C]: '+str(temperature))
        print('Relative Humidity [%]: '+str(humidity))
        # -------------------------
        # Send to Thingsboard
        # -------------------------
        print('Sending data to ThingsBoard')
        current_ts_ms = int(round(time.time() * 1000))   # current timestamp in milliseconds, needed for Thingsboard
        # send non-numeric data ('attributes') to Thingsboard as JSON. Example:
        # thingsboard_attributes = {'last_data_rate': str(payload['metadata']['data_rate'])}
        # thingsboard.sendDeviceAttributes(device_id, thingsboard_attributes)
        # send numeric data ('telemetry') to Thingsboard as JSON (only floats or integers!!!). Example:
        thingsboard_telemetry = {'temperature': temperature,
                                 'humidity': humidity}
                                 # 'latitude': float(payload['latitude']),
                                 # 'longitude': float(payload['longitude'])}
        self.thingsboard.sendDeviceTelemetry(device_id.lower(), current_ts_ms, thingsboard_telemetry)