// Deep WebSocket capture - multiple hooks
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Deep WebSocket Capture\n");

        // ============ Hook RealWebSocket directly ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            // Send
            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> OUT: " + text.substring(0, 500));
                return this.send(text);
            };
            console.log("[+] RealWebSocket.send hooked");

            // Try to hook internal reader callback
            try {
                var MessageCallback = Java.use("okhttp3.internal.ws.RealWebSocket$1");
                if (MessageCallback) {
                    console.log("[+] Found RealWebSocket$1");
                }
            } catch(e) {}

        } catch(e) {
            console.log("[-] RealWebSocket error: " + e);
        }

        // ============ Hook WebSocketReader ============
        try {
            var WebSocketReader = Java.use("okhttp3.internal.ws.WebSocketReader");

            // Try different read methods
            var readerMethods = WebSocketReader.class.getDeclaredMethods();
            for (var i = 0; i < readerMethods.length; i++) {
                var m = readerMethods[i];
                console.log("[READER] " + m.getName() + " " + m.getParameterTypes());
            }
        } catch(e) {
            console.log("[-] Reader error: " + e);
        }

        // ============ Hook all subclasses of WebSocketListener ============
        try {
            var WebSocketListener = Java.use("okhttp3.WebSocketListener");

            WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                console.log("\n<<< IN (Listener): " + text.substring(0, 2000));
                return this.onMessage(ws, text);
            };

            WebSocketListener.onOpen.implementation = function(ws, response) {
                console.log("\n[WS OPEN] Connected");
                return this.onOpen(ws, response);
            };

            WebSocketListener.onFailure.implementation = function(ws, t, response) {
                console.log("\n[WS FAIL] " + t);
                return this.onFailure(ws, t, response);
            };

            console.log("[+] WebSocketListener hooks applied");
        } catch(e) {
            console.log("[-] Listener error: " + e);
        }

        // ============ Look for Centrifuge ============
        try {
            var CentrifugeClient = Java.use("io.github.centrifugal.centrifuge.Client");
            console.log("[+] Found Centrifuge Client!");

            // Hook onMessage or similar
            var methods = CentrifugeClient.class.getDeclaredMethods();
            for (var i = 0; i < methods.length; i++) {
                console.log("[CENTRIFUGE] " + methods[i].getName());
            }
        } catch(e) {
            console.log("[-] No Centrifuge: " + e.message);
        }

        // ============ Search for Avito messenger classes ============
        try {
            var found = [];
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf("socket") !== -1 &&
                        className.indexOf("avito") !== -1) {
                        found.push(className);
                    }
                },
                onComplete: function() {
                    console.log("\n[*] Avito socket classes:");
                    for (var i = 0; i < found.length && i < 20; i++) {
                        console.log("  " + found[i]);
                    }
                }
            });
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
