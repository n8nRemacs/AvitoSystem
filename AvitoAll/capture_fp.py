"""
Capture fingerprint via Frida Python API
"""
import frida
import sys
import time

JS_CODE = """
Java.perform(function() {
    console.log("[*] Fingerprint Capture Started");

    // Hook FingerprintStorage to get stored value
    try {
        var PrefFingerprintStorage = Java.use('f90.q');

        // Enumerate existing instances
        Java.choose('f90.q', {
            onMatch: function(instance) {
                console.log("\\n[FINGERPRINT FOUND]");
                console.log("fpx: " + instance.a());
                console.log("[END FINGERPRINT]");
            },
            onComplete: function() {}
        });

    } catch(e) {
        console.log("[-] Storage error: " + e);
    }

    // Also hook HTTP interceptor to see fingerprint in headers
    try {
        var Request = Java.use('okhttp3.Request');
        Request.header.overload('java.lang.String').implementation = function(name) {
            var value = this.header(name);
            if (name === 'f' && value) {
                console.log("\\n[HEADER f]: " + value);
            }
            return value;
        };
    } catch(e) {}
});
"""

def on_message(message, data):
    if message['type'] == 'send':
        print(message['payload'])
    elif message['type'] == 'error':
        print(f"Error: {message['stack']}")
    else:
        print(message)

def main():
    print("="*60)
    print("Avito Fingerprint Capture")
    print("="*60)

    try:
        # Get USB device
        device = frida.get_usb_device(timeout=5)
        print(f"[+] Device: {device.name}")

        # Find Avito PID
        print("[*] Looking for Avito process...")
        avito_pid = None
        for app in device.enumerate_applications():
            if app.identifier == "com.avito.android" and app.pid > 0:
                avito_pid = app.pid
                print(f"[+] Found Avito PID: {avito_pid}")
                break

        if not avito_pid:
            print("[-] Avito not running! Please open Avito app.")
            return

        # Attach by PID
        print(f"[*] Attaching to PID {avito_pid}...")
        session = device.attach(avito_pid)
        print("[+] Attached!")

        # Create script
        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()

        print("\n[*] Script loaded. Waiting for fingerprint...")
        print("[*] Make any action in Avito app to trigger capture")
        print("[*] Press Ctrl+C to stop\n")

        # Wait
        time.sleep(30)

    except frida.ServerNotRunningError:
        print("[-] Frida server not running on device!")
    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
