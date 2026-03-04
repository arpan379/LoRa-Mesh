from machine import Pin, Timer
# from time import sleep_ms
import ubluetooth
from sx1262 import SX1262
# import network
# import usocket as socket
import time
import _thread

#sending Constants 
CHUNK_SIZE = 100  # Bytes per packet
ACK_TIMEOUT = 3   # Seconds to wait for ACK
MAX_RETRIES = 5   # Maximum retry attempts per chunk
#global file sent flag variable
sending_file_status = False
send_msg_queue = []

#receiving constants
received_chunks = {}
expected_total = None
received_file = b''
file_name = "received_file.txt" 
recv_msg_queue = []

#Global latest message variables
# latest_message_recv = 'No message received yet'
# latest_message_send = 'No message sent yet'

# Global file content to send
file_data = b''

# LoRa Init
sx = SX1262(spi_bus=1, clk=Pin(36), mosi=Pin(37), miso=Pin(38), cs=Pin(35), irq=Pin(42), rst=Pin(39), gpio=Pin(40))
# sx = SX1262(spi_bus=1, clk=36, mosi=37, miso=38, cs=35, irq=42, rst=39, gpio=40)
#sx = SX1262(spi_bus=1, clk=18, mosi=33, miso=34, cs=17, irq=42, rst=35, gpio=36)

sx.begin(
    freq=866, 
    bw=125.0, 
    sf=7, 
    cr=8, 
    syncWord=0x1424,
    power=17, 
    currentLimit=60.0, 
    preambleLength=8,
    crcOn=True, 
    tcxoVoltage=1.7,
    blocking=True)

# sx.begin(
#     freq=866, 
#     bw=125.0, 
#     sf=12, 
#     cr=8, 
#     syncWord=0x1424,
#     power=22, 
#     currentLimit=60.0, 
#     preambleLength=8,
#     crcOn=True, 
#     tcxoVoltage=1.7,
#     blocking=True)



#BLE Name
ble_name = 'LoRa_Node-01'
#ble_name = 'LoRa_Node-02'


ble_msg = ""
last_location_link = ""  # Store the last complete received location URL

class ESP32_BLE:
    def _init_(self, name="ESP32S3_BLE"):
        print("INIT: BLE setup")
        self.name = name
        self.conn_handle = None
        self._should_advertise = False
        # self.led = Pin(2, Pin.OUT)
        self._recv_buffer = ""               # <-- buffer for partial writes

        self.ble = ubluetooth.BLE()
        self.ble.active(True)

        try:
            self.ble.config(mtu=128)
            print("DEBUG: MTU set to 128")
        except Exception as e:
            print("WARN: MTU config failed:", e)

        self.ble.irq(self.ble_irq)
        self._register_services()
        self._start_advertising()

    def ble_irq(self, event, data):
        global ble_msg, last_location_link, send_msg_queue

        if event == 1:  # CONNECT
            self.conn_handle = data[0]
            print("DEBUG: Connected handle=", self.conn_handle)
            # self.led.on()

        elif event == 2:  # DISCONNECT
            print("DEBUG: Disconnected")
            self.conn_handle = None
            # self.led.off()
            self._should_advertise = True

        elif event == 3:  # WRITE RECEIVED
            raw = self.ble.gatts_read(self.rx)
            chunk = raw.decode('utf-8')
            print("DEBUG: Got chunk:", repr(chunk))

            # accumulate
            self._recv_buffer += chunk

            # only proceed if we have at least one newline and "Location:" in buffer
            if "\n" in self._recv_buffer and "Location:" in self._recv_buffer:
                lines = self._recv_buffer.splitlines()
                # first non-empty line is your text
                text_line = lines[0].strip()
                # find the line that starts with "Location:"
                loc_line = next((l for l in lines if l.startswith("Location:")), "")
                url = loc_line.partition("Location:")[2].strip()
                last_location_link = url
                print("DEBUG: Parsed text:", text_line)
                print("DEBUG: Parsed URL:", last_location_link)

                # build reply
                response = text_line
                if last_location_link:
                    response += "\n"+last_location_link

                send_msg_queue.append(response)

                # clear buffer for next message
                self._recv_buffer = ""

                # send it
                # self._notify(response)

    def _register_services(self):
        UART_UUID = ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_UUID   = ubluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
        TX_UUID   = ubluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

        RX_CHR = (RX_UUID, ubluetooth.FLAG_WRITE)
        TX_CHR = (TX_UUID, ubluetooth.FLAG_NOTIFY)
        UART_SVC = (UART_UUID, (TX_CHR, RX_CHR))
        ((self.tx, self.rx),) = self.ble.gatts_register_services((UART_SVC,))
        print("DEBUG: Services registered")

    def _start_advertising(self):
        name_bytes = bytes(self.name, 'utf-8')
        adv = bytearray(b'\x02\x01\x02')
        adv += bytearray((len(name_bytes) + 1, 0x09)) + name_bytes
        self.ble.gap_advertise(100_000, adv)
        print("DEBUG: Advertising as:", self.name)

    def _notify(self, msg: str):
        if self.conn_handle is None:
            return
        try:
            mtu = self.ble.config('mtu')
        except:
            mtu = 23
        chunk_size = mtu - 3
        data = msg.encode('utf-8')
        for i in range(0, len(data), chunk_size):
            piece = data[i : i + chunk_size]
            try:
                self.ble.gatts_notify(self.conn_handle, self.tx, piece)
                print("DEBUG: Sent:", repr(piece))
                # sleep_ms(50)
            except Exception as e:
                print("ERROR: Notify failed:", e)


#locking variable
lock = _thread.allocate_lock()



def tx_msg_send(message):
    
    msg = message
    print('[TX] Message to send:', msg)

    for attempt in range(MAX_RETRIES):
        sx.send(msg.encode())
        cheak = False
            # Wait for ACK with timeout
        start_time = time.time()
        while time.time() - start_time < ACK_TIMEOUT:
            recv, err = sx.recv(len=0, timeout_en=True, timeout_ms=300)
            if recv:
                try:
                    if recv.decode().strip() == "ACK":
                        print(f"[ACK] Received ACK for message")
                        cheak = True
                        break  # Break out of ACK waiting loop
                except:
                    pass  # Ignore decode errors
            # time.sleep(0.1)
            else:  # No ACK received
                print(f"[TX] No ACK received, retrying...")
                continue  # Go to next attempt
        if cheak :
            break  # If we got here, we received ACK

    if attempt == MAX_RETRIES - 1 :
        print(f"[ERROR] Failed to send message after {MAX_RETRIES} attempts")
        return 
    



def sending_loop():

    while True :
        
        if len(send_msg_queue) :
            lock.acquire()
            print("sending lock aquired")
            msg_to_send = send_msg_queue.pop(0)
            tx_msg_send(msg_to_send)
            print("sending lock released")
            lock.release()


def receive_loop():
    global expected_total, received_chunks, received_file, file_name, recv_msg_queue, latest_message_recv
    print("LoRa receiver ready")

    while True:
        lock.acquire()
        #print("receive lock aquired")
        msg, err = sx.recv(len=0, timeout_en=True, timeout_ms=400)
        
        if msg:
            print(msg.decode().strip())
            try:
                parts = msg.split(b'|', 2)
                if len(parts) == 3:
                    index = int(parts[0])
                    total = int(parts[1])
                    chunk = parts[2]
                    
                    received_chunks[index] = chunk
                    print(f"[RX] Received chunk {index+1}/{total} ({len(chunk)} bytes)")
                    
                  
                    ack_msg = f"ACK{index+1}".encode()
                    sx.send(ack_msg)
                    
                    
                    # if total and len(received_chunks) == total:
                    #     received_file = b''.join([received_chunks[i] for i in sorted(received_chunks)])
                    #     received_file, file_name = extract_file_data(received_file)
                    #     print(f" File complete! Size: {len(received_file)} bytes")
                    #     print("Filename:", file_name)
                    #     print("File content preview:", received_file[:50]) 
                    #     received_chunks.clear()
                
                else :
                    recv_msg_queue.append(parts[0])
                    ack_msg = f"ACK".encode()
                    sx.send(ack_msg)

            except Exception as e:
                print(f"[RX Error] {str(e)}")
        #print("receive lock released")
        lock.release()


_thread.start_new_thread(receive_loop, ())

# ==== MAIN LOOP ====
ble = ESP32_BLE(ble_name)
while True:
    if ble._should_advertise:
        ble._should_advertise = False
        ble._start_advertising()
    
    if len(send_msg_queue) :
        lock.acquire()
        print("Msg lock aquired")
        tx_msg_send(send_msg_queue.pop(0))
        print("Msg lock released")
        lock.release()
    
    if len(recv_msg_queue) :
        ESP32_BLE._notify(recv_msg_queue.pop(0))
        
    # sleep_ms(500)


