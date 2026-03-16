// WebSocket incoming message capture via FrameCallback
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] WebSocket Incoming Message Capture\n");

        // ============ Hook FrameCallback.onReadMessage ============
        try {
            var FrameCallback = Java.use("okhttp3.internal.ws.WebSocketReader$FrameCallback");

            // There are 2 overloads: String and ByteString
            FrameCallback.onReadMessage.overload('java.lang.String').implementation = function(text) {
                console.log("\n╔═══════════════════════════════════════════════");
                console.log("║ <<< INCOMING MESSAGE (String)");
                console.log("╠═══════════════════════════════════════════════");
                console.log("║ " + text.replace(/\n/g, "\n║ "));
                console.log("╚═══════════════════════════════════════════════\n");
                return this.onReadMessage(text);
            };

            // ByteString is obfuscated as okio.o
            FrameCallback.onReadMessage.overload('okio.o').implementation = function(bytes) {
                var text = bytes.a();  // a() is likely utf8()
                console.log("\n╔═══════════════════════════════════════════════");
                console.log("║ <<< INCOMING MESSAGE (ByteString)");
                console.log("╠═══════════════════════════════════════════════");
                console.log("║ " + text.replace(/\n/g, "\n║ "));
                console.log("╚═══════════════════════════════════════════════\n");
                return this.onReadMessage(bytes);
            };

            console.log("[+] FrameCallback.onReadMessage hooked (both overloads)");
        } catch(e) {
            console.log("[-] FrameCallback error: " + e);
        }

        // ============ Hook Send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");
            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> SEND: " + text.substring(0, 400));
                return this.send(text);
            };
            console.log("[+] Send hooked");
        } catch(e) {}

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("\n[*] Ready! Incoming messages will now be captured.\n");
        console.log("[*] Open Avito, go to messages, and receive something!\n");
    });
}, 1000);
