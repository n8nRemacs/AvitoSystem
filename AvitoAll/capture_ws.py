"""
Capture WebSocket messages from Avito via Frida
"""
import frida
import time
import json

JS_CODE = """
setTimeout(function() {
    if (!Java.available) {
        console.log("[-] Java not available");
        return;
    }

    Java.perform(function() {
        console.log("[*] WebSocket capture started");

        // Hook OkHttp WebSocket
        try {
            var RealWebSocket = Java.use('okhttp3.internal.ws.RealWebSocket');

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\\n[WS SEND] " + text);
                return this.send(text);
            };

            console.log("[+] WebSocket send hooked");
        } catch(e) {
            console.log("[-] WS hook error: " + e);
        }

        // Hook WebSocket listener for received messages
        try {
            var WebSocketListener = Java.use('okhttp3.WebSocketListener');
            var classes = Java.enumerateLoadedClassesSync();

            classes.forEach(function(className) {
                if (className.includes('WebSocket') && className.includes('Listener')) {
                    try {
                        var cls = Java.use(className);
                        if (cls.onMessage) {
                            cls.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                                if (text.length < 5000) {
                                    console.log("\\n[WS RECV] " + text.substring(0, 500));
                                }
                                return this.onMessage(ws, text);
                            };
                        }
                    } catch(e) {}
                }
            });
        } catch(e) {}
    });
}, 2000);
"""

def on_message(msg, data):
    if msg['type'] == 'send':
        print(msg['payload'])
    elif msg['type'] == 'error':
        print(f"Error: {msg['stack']}")

def main():
    print("="*60)
    print("WebSocket Capture")
    print("="*60)

    device = frida.get_usb_device(timeout=5)
    print(f"[+] Device: {device.name}")

    # Find Avito
    avito_pid = None
    for app in device.enumerate_applications():
        if app.identifier == "com.avito.android" and app.pid > 0:
            avito_pid = app.pid
            break

    if not avito_pid:
        print("[-] Avito not running!")
        return

    print(f"[+] Avito PID: {avito_pid}")

    session = device.attach(avito_pid)
    script = session.create_script(JS_CODE)
    script.on('message', on_message)
    script.load()

    print("\n[*] Capturing... Open messenger in Avito app")
    print("[*] Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopped")

if __name__ == "__main__":
    main()
