// Capture ALL WebSocket messages - especially incoming pushes
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Push Notification Capture - Capturing ALL messages\n");

        // ============ WebSocket Send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> OUT >>> " + text.substring(0, 300));
                return this.send(text);
            };
            console.log("[+] WS send hooked");
        } catch(e) {
            console.log("[-] Send hook error: " + e);
        }

        // ============ WebSocket Receive - LOG EVERYTHING ============
        try {
            var WebSocketListener = Java.use("okhttp3.WebSocketListener");

            WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                // Log ALL incoming messages
                console.log("\n<<< IN <<<");
                console.log(text);
                console.log("<<< END <<<\n");
                return this.onMessage(ws, text);
            };
            console.log("[+] WS onMessage hooked - capturing ALL");
        } catch(e) {
            console.log("[-] onMessage hook error: " + e);
        }

        // ============ Alternative hooks for different WS implementations ============

        // Hook any class with "Listener" and "onMessage"
        try {
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf("avito") !== -1 &&
                        (className.indexOf("Listener") !== -1 ||
                         className.indexOf("Handler") !== -1 ||
                         className.indexOf("Callback") !== -1)) {
                        try {
                            var cls = Java.use(className);
                            var methods = cls.class.getDeclaredMethods();
                            for (var i = 0; i < methods.length; i++) {
                                var methodName = methods[i].getName();
                                if (methodName.indexOf("Message") !== -1 ||
                                    methodName.indexOf("message") !== -1 ||
                                    methodName.indexOf("receive") !== -1 ||
                                    methodName.indexOf("Receive") !== -1) {
                                    console.log("[FOUND] " + className + "." + methodName);
                                }
                            }
                        } catch(e) {}
                    }
                },
                onComplete: function() {
                    console.log("[*] Class enumeration complete");
                }
            });
        } catch(e) {}

        // ============ Hook Centrifuge (if used) ============
        try {
            var classes = [
                "io.github.centrifugal.centrifuge.Client",
                "io.github.centrifugal.centrifuge.Subscription",
                "com.avito.android.messenger.core.socket.SocketClient"
            ];

            classes.forEach(function(className) {
                try {
                    var cls = Java.use(className);
                    console.log("[+] Found: " + className);

                    var methods = cls.class.getDeclaredMethods();
                    for (var i = 0; i < methods.length; i++) {
                        console.log("  - " + methods[i].getName());
                    }
                } catch(e) {}
            });
        } catch(e) {}

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
            console.log("[+] SSL bypass active");
        } catch(e) {}

        console.log("\n[*] Waiting for incoming messages...");
        console.log("[*] Try sending yourself a message from another device!\n");
    });
}, 1000);
