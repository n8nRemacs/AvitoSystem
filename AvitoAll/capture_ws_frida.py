"""Capture WebSocket messages from real app"""
import frida
import time

JS_CODE = """
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] WebSocket capture started");

        // Hook WebSocket send
        var RealWebSocket = Java.use('okhttp3.internal.ws.RealWebSocket');

        RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
            console.log("\\n[WS SEND] " + text);
            return this.send(text);
        };

        // Hook the actual message writing
        try {
            var MessageQueue = Java.use('okhttp3.internal.ws.RealWebSocket$MessageQueue');
        } catch(e) {}

        console.log("[+] Hooks installed. Use messenger in app!");
    });
}, 1000);
"""

def on_message(msg, data):
    if msg['type'] == 'send':
        print(msg['payload'])
    elif msg['type'] == 'error':
        print(f"Error: {msg['stack'][:200]}")

def main():
    print("="*60)
    print("WebSocket Capture via Frida")
    print("="*60)

    device = frida.get_usb_device(timeout=5)
    print(f"[+] Device: {device.name}")

    # Find Avito
    pid = None
    for app in device.enumerate_applications():
        if app.identifier == "com.avito.android" and app.pid > 0:
            pid = app.pid
            break

    if not pid:
        print("[-] Avito not running!")
        return

    print(f"[+] Avito PID: {pid}")
    print("[*] Attaching...")

    session = device.attach(pid)
    script = session.create_script(JS_CODE)
    script.on('message', on_message)
    script.load()

    print("\n[*] Ready! Open messenger and send a message in the app")
    print("[*] Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopped")

if __name__ == "__main__":
    main()
