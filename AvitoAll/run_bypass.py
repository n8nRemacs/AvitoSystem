import frida
import sys
import time

script_path = "c:/Users/User/Documents/Revers/APK/Avito/avito_ssl_kill.js"

def on_message(message, data):
    if message['type'] == 'send':
        print(message['payload'])
    elif message['type'] == 'error':
        print('[ERROR]', message.get('description', message))
    else:
        # Handle console.log messages
        print(message)

device = frida.get_usb_device(timeout=5)
print(f"[*] Device: {device.name}")

# Kill existing Avito
try:
    device.kill("com.avito.android")
    time.sleep(1)
except:
    pass

# Spawn fresh
print("[*] Spawning Avito...")
pid = device.spawn(["com.avito.android"])
session = device.attach(pid)

with open(script_path, 'r') as f:
    script_code = f.read()

script = session.create_script(script_code)
script.on('message', on_message)
script.load()

device.resume(pid)
print(f"[*] Avito started (PID: {pid})")
print("[*] SSL Pinning bypass active!")
print("[*] Now login to Avito - traffic will go through Burp")
print("[*] Press Ctrl+C to stop\n")

try:
    sys.stdin.read()
except KeyboardInterrupt:
    pass
