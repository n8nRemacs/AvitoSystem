// Full WebSocket capture - both send and receive
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Full WebSocket Capture\n");

        // ============ WebSocket Send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> SEND >>>");
                console.log(text.substring(0, 3000));
                console.log(">>> END SEND >>>\n");
                return this.send(text);
            };
            console.log("[+] WS send hooked");
        } catch(e) {
            console.log("[-] WS send error: " + e);
        }

        // ============ WebSocket Receive - Method 1 ============
        try {
            var WebSocketListener = Java.use("okhttp3.WebSocketListener");

            WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                console.log("\n<<< RECEIVE <<<");
                console.log(text.substring(0, 5000));
                console.log("<<< END RECEIVE <<<\n");
                return this.onMessage(ws, text);
            };
            console.log("[+] WS onMessage hooked");
        } catch(e) {
            console.log("[-] WS onMessage error: " + e);
        }

        // ============ Alternative: Hook Avito's own WebSocket handler ============
        try {
            // Try to find Avito's messenger websocket classes
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf("avito") !== -1 &&
                        (className.indexOf("socket") !== -1 ||
                         className.indexOf("Socket") !== -1 ||
                         className.indexOf("messenger") !== -1)) {
                        console.log("[CLASS] " + className);
                    }
                },
                onComplete: function() {}
            });
        } catch(e) {}

        // ============ Hook MessageQueue or Reader ============
        try {
            var MessageReader = Java.use("okhttp3.internal.ws.WebSocketReader");

            MessageReader.processNextFrame.implementation = function() {
                var result = this.processNextFrame();
                console.log("[WS FRAME] processed");
                return result;
            };
            console.log("[+] WS reader hooked");
        } catch(e) {
            console.log("[-] WS reader error: " + e);
        }

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        try {
            var CertificatePinner = Java.use('okhttp3.CertificatePinner');
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function() {
                return;
            };
        } catch(e) {}

        console.log("\n[*] Ready!\n");
    });
}, 1000);
