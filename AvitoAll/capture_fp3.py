"""
Capture fingerprint via Frida - wait for Java
"""
import frida
import time

JS_CODE = """
function waitForJava() {
    if (Java.available) {
        Java.perform(function() {
            console.log("[*] Java available! Starting capture...");

            // Try SharedPreferences
            try {
                var ActivityThread = Java.use('android.app.ActivityThread');
                var context = ActivityThread.currentApplication().getApplicationContext();
                var prefs = context.getSharedPreferences("fp_storage", 0);
                var fpx = prefs.getString("fpx", null);
                if (fpx) {
                    console.log("\\n=== FINGERPRINT FOUND ===");
                    console.log("fpx: " + fpx);
                    console.log("========================\\n");
                }
            } catch(e) {
                console.log("[-] Prefs: " + e);
            }

            // Hook storage class
            try {
                var PrefFingerprintStorage = Java.use('f90.q');
                PrefFingerprintStorage.a.implementation = function() {
                    var result = this.a();
                    console.log("\\n=== FP FROM STORAGE ===");
                    console.log("fpx: " + result);
                    console.log("========================\\n");
                    return result;
                };
                console.log("[+] Storage hooked");
            } catch(e) {
                console.log("[-] Storage hook: " + e);
            }

            // Hook header interceptor
            try {
                var CallServerInterceptor = Java.use('okhttp3.internal.http.CallServerInterceptor');
                CallServerInterceptor.intercept.implementation = function(chain) {
                    var request = chain.request();
                    var f = request.header('f');
                    if (f) {
                        console.log("\\n=== HEADER f ===");
                        console.log(f);
                        console.log("================\\n");
                    }
                    return this.intercept(chain);
                };
                console.log("[+] Interceptor hooked");
            } catch(e) {
                console.log("[-] Interceptor: " + e);
            }
        });
    } else {
        console.log("[*] Waiting for Java...");
        setTimeout(waitForJava, 500);
    }
}

waitForJava();
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
    print("Avito Fingerprint Capture v3")
    print("="*60)

    try:
        device = frida.get_usb_device(timeout=5)
        print(f"[+] Device: {device.name}")

        print("[*] Spawning com.avito.android...")
        pid = device.spawn(["com.avito.android"])
        print(f"[+] Spawned PID: {pid}")

        session = device.attach(pid)
        print("[+] Attached!")

        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()

        device.resume(pid)
        print("[+] Resumed!")

        print("\n[*] Waiting for Java and fingerprint...")
        print("[*] Open any chat or search in Avito")
        print("[*] Press Ctrl+C to stop\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[*] Stopped")
    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
