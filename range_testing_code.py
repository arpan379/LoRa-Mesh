
from sx1262 import SX1262
import time
from machine import Pin

tx_or_rx = True # True if use tx mode and False if use rx mode
#tx_or_rx = False

# LoRa Init
sx = SX1262(spi_bus=1, clk=Pin(36), mosi=Pin(37), miso=Pin(38), cs=Pin(35), irq=Pin(42), rst=Pin(39), gpio=Pin(40))
#sx = SX1262(spi_bus=1, clk=36, mosi=37, miso=38, cs=35, irq=42, rst=39, gpio=40)
#sx = SX1262(spi_bus=1, clk=18, mosi=33, miso=34, cs=17, irq=42, rst=35, gpio=36)

# sx.begin(
#     freq=866, 
#     bw=125.0, 
#     sf=7, 
#     cr=8, 
#     syncWord=0x1424,
#     power=17, 
#     currentLimit=60.0, 
#     preambleLength=8,
#     crcOn=True, 
#     tcxoVoltage=1.7,
#     blocking=True)

sx.begin(
    freq=866, 
    bw=125.0, 
    sf=12, 
    cr=8, 
    syncWord=0x1424,
    power=22, 
    currentLimit=140.0, 
    preambleLength=16,
    crcOn=True, 
    tcxoVoltage=1.7,
    blocking=True)

time_on_air = sx.getTimeOnAir(18)  
print(f"Estimated airtime: {time_on_air:.3f} seconds")
if tx_or_rx:
    msg = "Hi I am Arpan Dutta"
    while True :
        sx.send(msg.encode())
else:
    f1 = open("Received_msg.txt","w")
    while True :
        i = 0
        start = time.time()
        recv, err = sx.recv()
        end = time.time()
        print(f"msg received : {recv.decode().strip()}\ttime taken : {end-start}\tmsg no. : {i}")
        
        f1.write(f"msg received : {recv.decode().strip()}\ttime taken : {end-start}\tmsg no. : {i}")

        i = i+1
        
     

