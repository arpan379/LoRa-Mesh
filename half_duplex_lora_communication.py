
from sx1262 import SX1262
import network
import usocket as socket
import time
import _thread
import re

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
latest_message_recv = 'No message received yet'
latest_message_send = 'No message sent yet'

#wifi credentials
ssid = 'LoRa_Node-01'
#ssid = 'LoRa_Node-02'
password ='esp32s31234'

# Global file content to send
file_data = b''

# LoRa Init
sx = SX1262(spi_bus=1, clk=36, mosi=37, miso=38, cs=35, irq=42, rst=39, gpio=40)
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
#     currentLimit=140.0, 
#     preambleLength=16,
#     crcOn=True, 
#     tcxoVoltage=1.7,
#     blocking=True)

chunk_time_on_air = sx.getTimeOnAir(CHUNK_SIZE) # calculating how much ms it takes to transmit or receive CHUNK_SIZE bytes of data

# Setup SoftAP
ap = network.WLAN(network.AP_IF)
ap.active(False)
time.sleep(0.5)
ap.active(True)
ap.config(essid = ssid, password = password)
print('SoftAP started, IP:', ap.ifconfig()[0])

#locking variable
lock = _thread.allocate_lock()

#Function for html webpage
def web_page():
    return f"""<html><body>
    <h2>Upload Text File</h2>
    <form enctype="multipart/form-data" method="POST">
        <input name="file" type="file"/>
        <input type="submit" value="Upload"/>
    </form>
    <form action="/download" method="GET">
        <textarea rows="15" cols="80" style="font-family: monospace;">{received_file}</textarea><br>
        <button type="submit">Download File</button>
    </form>
    <h4>Received File: {file_name}</h4>
    <h2><p><b>Last Message sent:</b> {latest_message_send}</p></h2>
    <form action="/send" method="GET">
        <input type="text" name="msg" placeholder="Type message here">
        <input type="submit" value="Send">
    </form>
    <h2><p><b>Last Message Received:</b> {latest_message_recv}</p></h2>
    </body></html>"""


def tx_msg_send(req):
    
    global send_msg_queue, latest_message_send

    msg_ack_time_on_air = sx.getTimeOnAir(len("ACK")) # calculating how much ms it takes to transmit or receive ("ACK")this much bytes of data

    msg_index = req.find(b'/send?msg=') + len(b'/send?msg=')
    msg_end = req.find(b' ', msg_index)
    msg = req[msg_index:msg_end].replace(b'+', b' ')
    send_msg_queue.append(msg.decode()) 
    print('[TX] Message to send:', msg.decode())

    if len(send_msg_queue) :
        latest_message_send = send_msg_queue.pop(0)


    for attempt in range(MAX_RETRIES):
        sx.send(msg)
        cheak = False
        # Wait for ACK with timeout
        start_time = time.time()
        while time.time() - start_time < ACK_TIMEOUT:
            recv, err = sx.recv(len=0, timeout_en=True, timeout_ms=msg_ack_time_on_air)
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


def send_file(data):

    global sending_file_status

    if not data:      #if there is no dada
        print("No data to send!")
        return

    #calculating the total no of chunks    
    total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE  
    print(f"Sending file in {total_chunks} chunks ({len(data)} bytes total)")
    
    for i in range(total_chunks):
        #slicing the data into chunks
        chunk = data[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]      
        packet = b'%d|%d|' % (i, total_chunks) + chunk
        
        ack_time_on_air = sx.getTimeOnAir(len(f"ACK{i}")) # calculating how much ms it takes to transmit or receive (f"ACK{i}") this much bytes of data

        for attempt in range(MAX_RETRIES):
            sx.send(packet)
            print(f"[TX] Sent chunk {i+1}/{total_chunks} (attempt {attempt+1}/{MAX_RETRIES})")
            cheak = False
            # Wait for ACK with timeout
            start_time = time.time()
            while time.time() - start_time < ACK_TIMEOUT:
                recv, err = sx.recv(len=0, timeout_en=True, timeout_ms=ack_time_on_air)
                if recv:
                    try:
                        if recv.decode().strip() == f"ACK{i}":
                            print(f"[ACK] Received ACK for chunk {i}")
                            cheak = True
                            break  # Break out of ACK waiting loop
                    except:
                        pass  # Ignore decode errors
                # time.sleep(0.1)
                else:  # No ACK received
                    print(f"[TX] No ACK for chunk {i}, retrying...")
                    continue  # Go to next attempt
            if cheak :
                break  # If we got here, we received ACK

        if attempt == MAX_RETRIES - 1 :
            print(f"[ERROR] Failed to send chunk {i} after {MAX_RETRIES} attempts")
            return
        
        if i == total_chunks - 1 :
            sending_file_status = True


#This function just slice the fila data part fron the http request
def parse_post(data):
    boundary = data.split(b'\r\n')[0]
    parts = data.split(boundary)
    
    for part in parts:
        if b'filename="' in part:
            file_start = part.find(b'\r\n\r\n') + 4
            file_end = part.rfind(b'\r\n')
            if file_end > file_start:
                return part[file_start:file_end]
    return b''


def extract_file_data(raw_data):
    # """Extract the actual file content from multipart form data"""
    try:
        
        boundary_pattern = b'------WebKitFormBoundary[^\r\n]+'
        match = re.search(boundary_pattern, raw_data)
        if not match:
            return raw_data, "received_file.txt"  
        
        boundary = match.group(0)
        parts = raw_data.split(boundary)
        
        for part in parts:
            if b'filename="' in part:
               
                filename_match = re.search(b'filename="([^"]+)"', part)
                if filename_match:
                    filename = filename_match.group(1).decode('utf-8')
                else:
                    filename = "received_file.txt"
                
            
                header_end = part.find(b'\r\n\r\n')
                if header_end != -1:
                    content_start = header_end + 4
                    content_end = part.rfind(b'\r\n')
                    if content_end > content_start:
                        return part[content_start:content_end], filename
        return raw_data, "received_file.txt"  
    except Exception as e:
        print("Error extracting file data:", e)
        return raw_data, "received_file.txt"
    

def receive_loop():
    global expected_total, received_chunks, received_file, file_name, recv_msg_queue, latest_message_recv
    print("LoRa receiver ready")

    while True:
        lock.acquire()
        #print("receive lock aquired")
        msg, err = sx.recv(len=0, timeout_en=True, timeout_ms=chunk_time_on_air)
        
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
                    
                  
                    ack_msg = f"ACK{index}".encode()
                    sx.send(ack_msg)
                    
                    
                    if total and len(received_chunks) == total:
                        received_file = b''.join([received_chunks[i] for i in sorted(received_chunks)])
                        received_file, file_name = extract_file_data(received_file)
                        print(f" File complete! Size: {len(received_file)} bytes")
                        print("Filename:", file_name)
                        print("File content preview:", received_file[:50]) 
                        received_chunks.clear()
                
                else :
                    recv_msg_queue.append(parts[0])
                    ack_msg = f"ACK".encode()
                    sx.send(ack_msg)
                    if len(recv_msg_queue) :
                        latest_message_recv = recv_msg_queue.pop(0)
                        latest_message_recv = latest_message_recv.decode()

            except Exception as e:
                print(f"[RX Error] {str(e)}")
        #print("receive lock released")
        lock.release()
        



def web_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(1)
    print("Web server running at http://192.168.4.1")
    

    while True:
        conn, addr = s.accept()
        print("Client connected:", addr)

        req = conn.recv(8192)
        print(f"received req : {req}")

        if b'POST' in req:
            lock.acquire()
            print("post lock aquired")

            file_data = parse_post(req)
            if file_data:
                print(f"[WEB] File received ({len(file_data)} bytes), sending...")
                send_file(file_data)
                if sending_file_status :
                    response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nSome ERROR occured while sending the file!"
                else :
                    response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nFile Sent successfully!"
                conn.send(response)
            else:
                response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/html\r\n\r\nNo file data found!"
                conn.send(response)
            print("post lock released")
            lock.release()

        elif b'GET /download' in req:
            
            headers = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Disposition: attachment; filename={file_name}\r\n"
                "Content-Type: application/octet-stream\r\n"
                f"Content-Length: {len(received_file)}\r\n"
                "\r\n"
            )
            conn.send(headers.encode())
            conn.send(received_file)
        
        elif b'GET /send?' in req:
            lock.acquire()
            print("Msg lock aquired")
            tx_msg_send(req)
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + web_page()
            conn.send(response)
            print("Msg lock released")
            lock.release()

        else:
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + web_page()
            conn.send(response)

        conn.close()


_thread.start_new_thread(receive_loop, ())
web_server()