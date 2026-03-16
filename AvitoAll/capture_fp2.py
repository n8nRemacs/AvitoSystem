"""
Capture fingerprint via Frida - Spawn mode
"""
import frida
import time

JS_CODE = """
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] Fingerprint Capture Started");

        // Try to get fingerprint from SharedPreferences directly
        try {
            var Context = Java.use('android.content.Context');
            var ActivityThread = Java.use('android.app.ActivityThread');
            var context = ActivityThread.currentApplication().getApplicationContext();

            var prefs = context.getSharedPreferences("fp_storage", 0);
            var fpx = prefs.getString("fpx", null);
            if (fpx) {
                console.log("\\n[FINGERPRINT FROM PREFS]");
                console.log("fpx: " + fpx);
                console.log("[END]");
            }
        } catch(e) {
            console.log("[-] Prefs error: " + e);
        }

        // Hook FingerprintStorage class
        try {
            var PrefFingerprintStorage = Java.use('f90.q');

            PrefFingerprintStorage.a.implementation = function() {
                var result = this.a();
                console.log("\\n[FP STORAGE] fpx: " + result);
                return result;
            };

            console.log("[+] FingerprintStorage hooked");
        } catch(e) {
            console.log("[-] Storage hook error: " + e);
        }

        // Hook the header provider
        try {
            var N = Java.use('com.avito.android.remote.interceptor.N');
            N.getF253512a.implementation = function() {
                var result = this.getF253512a();
                console.log("\\n[HEADER PROVIDER] f: " + result);
                return result;
            };
            console.log("[+] Header provider hooked");
        } catch(e) {
            console.log("[-] Header provider error: " + e);
        }
    });
}, 3000);
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
    print("Avito Fingerprint Capture (Spawn Mode)")
    print("="*60)

    try:
        device = frida.get_usb_device(timeout=5)
        print(f"[+] Device: {device.name}")

        print("[*] Spawning com.avito.android...")
        pid = device.spawn(["com.avito.android"])
        print(f"[+] Spawned with PID: {pid}")

        print("[*] Attaching...")
        session = device.attach(pid)
        print("[+] Attached!")

        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()

        print("[*] Resuming app...")
        device.resume(pid)
        print("[+] App resumed!")

        print("\n[*] Waiting 5 seconds for Java to load...")
        time.sleep(5)

        print("[*] Waiting for fingerprint... Make any request in Avito")
        print("[*] Will run for 60 seconds\n")

        time.sleep(60)

    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
