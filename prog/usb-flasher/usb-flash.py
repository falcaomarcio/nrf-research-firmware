#!/usr/bin/env python3

'''
  Copyright (C) 2016 Bastille Networks

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import usb.core
import usb.util
import time
import sys
import array
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s.%(msecs)03d]  %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

# Check pyusb dependency - No changes needed in Python 3
try:
    from usb import core as _usb_core
except ImportError as ex:  # Changed from , to as
    print('''
------------------------------------------
| PyUSB was not found or is out of date. |
------------------------------------------

Please update PyUSB using pip:

pip3 install -U -I pip && pip3 install -U -I pyusb  # Use pip3 for Python 3
''')
    sys.exit(1)

# USB timeout sufficiently long for operating in a VM
usb_timeout = 2500

# Verify that we received a command line argument
if len(sys.argv) < 2:
    print('Usage: ./usb-flash.py path-to-firmware.bin')  # print() is a function in Python 3
    quit()

# Read in the firmware
with open(sys.argv[1], 'rb') as f:
    data = f.read()

# Zero pad the data to a multiple of 512 bytes
data += b'\000' * (512 - len(data) % 512)  # Use b'' for byte literals in Python 3

# Find an attached device running CrazyRadio or RFStorm firmware
logging.info("Looking for a compatible device that can jump to the Nordic bootloader")
product_ids = [0x0102, 0x7777]
for product_id in product_ids:
    try:
        dongle = usb.core.find(idVendor=0x1915, idProduct=product_id)

        if dongle is None:
            continue

        # Device found, instruct it to jump to the Nordic bootloader
        logging.info("Device found, jumping to the Nordic bootloader")
        if product_id == 0x0102:
            dongle.write(0x01, [0xFF], timeout=usb_timeout)
        else:
            dongle.ctrl_transfer(0x40, 0xFF, 0, 0, None, timeout=usb_timeout)  # Changed () to None
        try:
            usb.util.dispose_resources(dongle)  # Release USB resources before reset
            dongle.reset()
        except:
            pass
    except Exception as e:
        logging.error(f"Error finding or resetting device: {e}")
        continue

# Find an attached device running the Nordic bootloader
logging.info("Looking for a device running the Nordic bootloader")
start = time.time()
while time.time() - start < 1:
    try:
        dongle = usb.core.find(idVendor=0x1915, idProduct=0x0101)
        if dongle is not None:
            dongle.set_configuration()
            break
    except AttributeError:
        continue

# Verify that we found a compatible device
if not dongle:
    logging.info("No compatible device found")
    raise Exception('No compatible device found.')

# Write the data, one page at a time
logging.info("Writing image to flash")
page_count = len(data) // 512  # Use // for integer division in Python 3
for page in range(page_count):
    # Tell the bootloader that we are going to write a page
    dongle.write(0x01, [0x02, page])
    dongle.read(0x81, 64, timeout=usb_timeout)

    # Write the page as 8 pages of 64 bytes
    for block in range(8):
        block_write = data[page * 512 + block * 64:page * 512 + block * 64 + 64]
        dongle.write(0x01, list(block_write), timeout=usb_timeout)  # Convert block_write to list
        dongle.read(0x81, 64, timeout=usb_timeout)

# Verify that the image was written correctly
logging.info("Verifying write")
block_number = 0
for page in range(page_count):
    dongle.write(0x01, [0x06, 0], timeout=usb_timeout)
    dongle.read(0x81, 64, timeout=usb_timeout)

    for block in range(8):
        dongle.write(0x01, [0x03, block_number], timeout=usb_timeout)
        block_read = array.array('B', dongle.read(0x81, 64, timeout=usb_timeout)).tobytes()  # tostring() is deprecated, use tobytes()
        if block_read != data[block_number * 64:block_number * 64 + 64]:
            raise Exception('Verification failed on page {0}, block {1}'.format(page, block))
        block_number += 1

logging.info("Firmware programming completed successfully")
logging.info("\033[92m\033[1mPlease unplug your dongle or breakout board and plug it back in.\033[0m")