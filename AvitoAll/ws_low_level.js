// Low-level WebSocket capture
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Low-Level WebSocket Capture\n");

        // ============ Hook RealWebSocket internal methods ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            // Send
            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> OUT: " + text.substring(0, 400));
                return this.send(text);
            };

            // Hook onReadMessage - this is the callback that receives messages
            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                console.log("\n<<< IN (String): " + text);
                return this.onReadMessage(text);
            };

            try {
                RealWebSocket.onReadMessage.overload('okio.o').implementation = function(bytes) {
                    console.log("\n<<< IN (Bytes): " + bytes.a());
                    return this.onReadMessage(bytes);
                };
            } catch(e) {}

            console.log("[+] RealWebSocket hooked");
        } catch(e) {
            console.log("[-] RealWebSocket error: " + e);
        }

        // ============ Hook WebSocketReader.processNextFrame ============
        try {
            var WebSocketReader = Java.use("okhttp3.internal.ws.WebSocketReader");

            WebSocketReader.processNextFrame.implementation = function() {
                console.log("[FRAME] Processing...");
                var result = this.processNextFrame();
                console.log("[FRAME] Result: " + result);
                return result;
            };
            console.log("[+] WebSocketReader.processNextFrame hooked");
        } catch(e) {
            console.log("[-] processNextFrame error: " + e);
        }

        // ============ Try to hook OkHttp EventListener ============
        try {
            var EventListener = Java.use("okhttp3.EventListener");
            console.log("[+] EventListener found");
        } catch(e) {}

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("\n[*] Ready!\n");
    });
}, 1000);
