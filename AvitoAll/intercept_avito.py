import frida
import sys
import time

SCRIPT = """
Java.perform(function() {
    console.log("[*] Avito HTTP Interceptor loaded");

    // Hook OkHttp3 RealCall
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();

            if (url.indexOf("avito") !== -1 || url.indexOf("socket") !== -1) {
                console.log("\\n[REQUEST] " + request.method() + " " + url);

                var headers = request.headers();
                var size = headers.size();
                for (var i = 0; i < size; i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }

                // Try to get body
                var body = request.body();
                if (body !== null) {
                    console.log("  [Body] " + body.contentType());
                }
            }
            return this.execute();
        };
        console.log("[+] Hooked RealCall.execute");
    } catch(e) {
        console.log("[-] RealCall hook error: " + e);
    }

    // Hook async calls
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        RealCall.enqueue.implementation = function(callback) {
            var request = this.request();
            var url = request.url().toString();

            if (url.indexOf("avito") !== -1) {
                console.log("\\n[ASYNC REQUEST] " + request.method() + " " + url);

                var headers = request.headers();
                var size = headers.size();
                for (var i = 0; i < size; i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }
            return this.enqueue(callback);
        };
        console.log("[+] Hooked RealCall.enqueue");
    } catch(e) {
        console.log("[-] enqueue hook error: " + e);
    }

    // Hook Request.Builder to catch headers being added
    try {
        var Builder = Java.use("okhttp3.Request$Builder");
        Builder.addHeader.implementation = function(name, value) {
            if (name.toString().startsWith("X-") || name.toString().toLowerCase().indexOf("auth") !== -1) {
                console.log("[ADD HEADER] " + name + ": " + value);
            }
            return this.addHeader(name, value);
        };
        console.log("[+] Hooked Request.Builder.addHeader");
    } catch(e) {
        console.log("[-] Builder hook error: " + e);
    }

    console.log("[*] Hooks installed! Interact with Avito app...");
});
"""

def on_message(message, data):
    if message['type'] == 'send':
        print(message['payload'])
    elif message['type'] == 'error':
        print('[ERROR]', message['description'])
    else:
        print(message)

def main():
    device = frida.get_usb_device(timeout=5)
    print(f"[*] Connected to {device.name}")

    # Try to attach to running process first
    try:
        session = device.attach("com.avito.android")
        print("[*] Attached to running Avito")
    except frida.ProcessNotFoundError:
        print("[*] Spawning Avito...")
        pid = device.spawn(["com.avito.android"])
        session = device.attach(pid)
        device.resume(pid)
        print(f"[*] Spawned and attached (PID: {pid})")

    script = session.create_script(SCRIPT)
    script.on('message', on_message)
    script.load()

    print("[*] Press Ctrl+C to stop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping...")
        session.detach()

if __name__ == "__main__":
    main()
