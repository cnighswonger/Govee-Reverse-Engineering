#!/usr/bin/python3
import asyncio
import logging
import time
from bleak import BleakClient
from utils import find_device, compute_xor, SEND_CHARACTERISTIC_UUID, RECV_CHARACTERISTIC_UUID
from pprint import pprint

## Configuration
DEVICE_NAME = "GVH508668B9"  # the name of the device we want to pair with
AUTH_KEY = "5d0f273ef04b9f4f"  # Obtain this using pair.py

MSG_TURN_ON = "3301ff00000000000000000000000000000000cd"
MSG_TURN_OFF = "3301f000000000000000000000000000000000c2"
MSG_SND_PWR_DATA = "aa000000000000000000000000000000000000aa"

READ_DATA_UUID = "000102030405060708090a0b0c0d2b10"

logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s %(levelname)s: %(message)s",
    )
logger = logging.getLogger(__name__)
# logger.level = logging.DEBUG

async def main():
  logger.info(f"Searching for device {DEVICE_NAME}")
  device, adv_data = await find_device(DEVICE_NAME)
  #logger.info(f"Adv Data: {adv_data}")
  if device is None:
    logger.error(f"Could not find a device!")
    return

  # Read the state of the switch at this moment
  is_on = get_adv_on_state(adv_data)
  if is_on is None:
    logger.error(f"Could not detect the current state")
    return
  logger.info(f"Device state is: {is_on}")

  logger.info(f"Connecting...")

  # Connect 
  async with BleakClient(device.address) as client:
    logger.info(f"Connected to {client.address}")
    
    # events to control execution flow
    on_auth_ready = asyncio.Event()
    on_get_power_data_ready = asyncio.Event()

    async def handle_notification(c, data):
      if data[0] == 0x33 and data[1] == 0xB2:
        on_auth_ready.set()
      elif (data.hex()[0:4] != "ee19"):
        logger.info(f"Discarding packet.")
      else:
        powerData = {
          "raw"         : data.hex(),
          "timestamp"   : time.time(),
          "localtime"   : time.strftime("%H:%M:%S", time.localtime(time.time())),
          "runtime"     : int(data.hex()[4:10],16),
          "kWh"         : int(data.hex()[10:16],16)/10000,
          "volts"       : int(data.hex()[16:20],16)/100,
          "amps"        : int(data.hex()[20:24],16)/100,
          "watts"       : int(data.hex()[26:30],16)/100,
          "powerfactor" : int(data.hex()[30:32],16)
        }
        logger.info(f"Current power data:")
        pprint(powerData, indent=4, sort_dicts=False)
        on_get_power_data_ready.set()

    await client.start_notify(RECV_CHARACTERISTIC_UUID, handle_notification)
    
    await authenticate(client, AUTH_KEY)
    await on_auth_ready.wait()

    await get_power_data(client)
    await on_get_power_data_ready.wait()

    await client.stop_notify(RECV_CHARACTERISTIC_UUID)
    logger.info("Finished")



# Parses the advertisement data for useful information (i.e. the on/off state)
def get_adv_on_state(adv_data):
    for mfr_id, mfr_data in adv_data.manufacturer_data.items():
      #data = mfr_data.decode()
      logger.info(f"Data: {mfr_data}")
      # The next to last byte in the manufacturer data is the state of the switch
      return mfr_data[-2] == 0x01
    return None

async def authenticate(client, auth_key):
  logger.info("Authenticating")
  # Create the message
  ba = bytearray([0x33, 0xB2]) + bytearray.fromhex(auth_key).ljust(17, b'\0')
  ba.append(compute_xor(ba))  
  logger.debug(f"SEND {ba.hex()}")
  await client.write_gatt_char(SEND_CHARACTERISTIC_UUID, ba)

async def set_state(client, new_state):
  logger.info(f"Updating state to: {new_state}")
  # Send the set on or off command
  ba = bytearray.fromhex(MSG_TURN_ON if new_state else MSG_TURN_OFF)
  logger.debug(f"SEND {ba.hex()}")
  await client.write_gatt_char(SEND_CHARACTERISTIC_UUID, ba)

async def get_power_data(client):
  logger.info(f"Retrieving power data.")
  # Send the command to retrieve the current power data
  ba = bytearray.fromhex(MSG_SND_PWR_DATA)
  logger.debug(f"SEND {ba.hex()}")
  await client.write_gatt_char(SEND_CHARACTERISTIC_UUID, ba)
  logger.info(f"Done retrieving power data.")

asyncio.run(main())
