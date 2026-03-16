// Simple WebSocket capture - no class enumeration
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Simple Push Capture\n");

        // ============ WebSocket Send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> SEND: " + text.substring(0, 500));
                return this.send(text);
            };
            console.log("[+] WS send hooked");
        } catch(e) {
            console.log("[-] Send error: " + e);
        }

        // ============ WebSocket Receive ============
        try {
            var WebSocketListener = Java.use("okhttp3.WebSocketListener");

            WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                console.log("\n<<< RECV: " + text);
                return this.onMessage(ws, text);
            };
            console.log("[+] WS receive hooked");
        } catch(e) {
            console.log("[-] Receive error: " + e);
        }

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("\n[*] Ready! Open messages and wait for incoming...\n");
    });
}, 1000);
