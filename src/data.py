import serial
import paho.mqtt.client as mqtt
import random
import pandas as pd
from datetime import datetime
import re
import paho.mqtt.enums as mqtt_enum
import json
import ssl
from time import sleep
from decouple import config

def data_process():
    # MQTT broker configuration
    broker_address = config("BROKER_ADDRESS", cast=str)  # Replace with your MQTT broker address
    broker_port = config("BROKER_PORT", cast=int)  # Default MQTT port
    rootCa = "/greengrass/v2/rootCA.pem"
    thingCert = "/greengrass/v2/thingCert.crt"
    privKey = "/greengrass/v2/privKey.key"

    # Serial port configuration
    puerto_serial = '/dev/ttyUSB0'  # Change this to the correct serial port on your system
    velocidad = 9600  # Change this to the correct baud rate

    # Topics
    input_topic = "hardware_status"
    output_topic = "sensor/ESP32"

    # Expresiones regulares para extraer valores de sensores
    accelerometer_pattern = re.compile(r'Accelerometer \(g\): X = (.*), Y = (.*), Z = (.*)')
    gyroscope_pattern = re.compile(r'Gyroscope \(degrees/s\): X = (.*), Y = (.*), Z = (.*)')
    temperature_pattern = re.compile(r'Temperature: (.*) °C')
    humidity_pattern = re.compile(r'Humidity: (.*) %')

    # Callback function to handle connection established event
    def on_connect(client, userdata, flags, rc):
        print("Connected to MQTT broker with result code "+str(rc))
        # Subscribe to the input topic
        client.subscribe(input_topic)
        client.subscribe(output_topic)

    # Callback function to handle message received event
    def on_message(client, userdata, msg):
        print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")

    ser = None  # Inicializamos ser
    while True:
        try:
            # Open the serial connection
            ser = serial.Serial(puerto_serial, velocidad, timeout=1, rtscts=True, dsrdtr=True)
            break  # Exit the loop if connection is successful
        except Exception as e:
            print("Serial port connection error:", e)
            print("Retrying in 5 seconds...")
            sleep(5)  # Wait for 5 seconds before retrying


    # Create an empty dataframe
    df = pd.DataFrame(columns=['Timestamp', 'Accelerometer_X', 'Accelerometer_Y', 'Accelerometer_Z',
                            'Gyroscope_X', 'Gyroscope_Y', 'Gyroscope_Z', 'Temperature', 'Humidity'])

    # Create MQTT client instance
    client_id = f'python-mqtt-{random.randint(0, 1000)}'
    client = mqtt.Client(callback_api_version=mqtt_enum.CallbackAPIVersion.VERSION1, client_id=client_id)

    # Set callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Configure certificates
    client.tls_set(ca_certs=rootCa, certfile=thingCert, keyfile=privKey, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)

    # Connect to MQTT broker
    connected = False
    while not connected:
        try:
            print("Attempting to connect to MQTT broker...")
            client.connect(broker_address, broker_port)
            connected = True
            print("Successfully connected to MQTT broker")
        except TimeoutError as e:
            print("Connection attempt timed out. Retrying in 5 seconds...")
            sleep(5)  # Wait for 5 seconds before retrying

    client.loop_start()

    try:
        while True:
            # Read a line of data from the serial port
            linea = ser.readline().decode().strip()

            # Get current timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Extract sensor data using regular expressions
            accelerometer_match = accelerometer_pattern.search(linea)
            gyroscope_match = gyroscope_pattern.search(linea)
            temperature_match = temperature_pattern.search(linea)
            humidity_match = humidity_pattern.search(linea)

            # Check if any sensor data is not None
            if any([
                accelerometer_match, gyroscope_match, temperature_match, humidity_match
            ]):
                # Append data to dataframe
                df = df._append({
                    'Timestamp': timestamp,
                    'Accelerometer_X': accelerometer_match.group(1) if accelerometer_match else None,
                    'Accelerometer_Y': accelerometer_match.group(2) if accelerometer_match else None,
                    'Accelerometer_Z': accelerometer_match.group(3) if accelerometer_match else None,
                    'Gyroscope_X': gyroscope_match.group(1) if gyroscope_match else None,
                    'Gyroscope_Y': gyroscope_match.group(2) if gyroscope_match else None,
                    'Gyroscope_Z': gyroscope_match.group(3) if gyroscope_match else None,
                    'Temperature': temperature_match.group(1) if temperature_match else None,
                    'Humidity': humidity_match.group(1) if humidity_match else None
                }, ignore_index=True)
                # Agrupar por timestamp y seleccionar el primer valor no nulo en cada grupo
                df_grouped = df.groupby('Timestamp').first().reset_index()
                print(df_grouped)
                
                # Publish data to the output topic
                try:
                    if not df_grouped.iloc[-1].isnull().any():
                        last_row = df_grouped.iloc[-1]
                        payload = json.dumps(last_row.to_dict())
                        client.publish(output_topic, payload, qos=1)
                    else:
                        print("El último registro contiene valores nulos.")
                except Exception as e:
                    print("Error al publicar en el topic:", output_topic)
                    print("Error:", e)

    except KeyboardInterrupt:
        print('Stopping serial port reading')
        ser.close()  # Close the serial connection

        # Save dataframe to a CSV file
        df_grouped.to_csv('data.csv', index=False)

        # Stop the MQTT client loop
        client.loop_stop()