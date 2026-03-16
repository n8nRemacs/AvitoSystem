// Avito-specific WebSocket capture
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito WebSocket Capture\n");

        // ============ Hook Avito WebSocket classes ============
        var avitoClasses = [
            "ru.avito.websocket.u",
            "ru.avito.websocket.u$a",
            "ru.avito.websocket.u$b",
            "ru.avito.websocket.u$c",
            "ru.avito.websocket.y",
            "ru.avito.websocket.y$a",
            "ru.avito.websocket.y$b"
        ];

        avitoClasses.forEach(function(className) {
            try {
                var cls = Java.use(className);
                console.log("\n[+] Hooking: " + className);

                var methods = cls.class.getDeclaredMethods();
                for (var i = 0; i < methods.length; i++) {
                    var method = methods[i];
                    var methodName = method.getName();
                    var paramTypes = method.getParameterTypes();

                    console.log("  Method: " + methodName + " (" + paramTypes.length + " params)");

                    // Hook methods that look like message handlers
                    if (methodName.indexOf("Message") !== -1 ||
                        methodName.indexOf("message") !== -1 ||
                        methodName.indexOf("receive") !== -1 ||
                        methodName.indexOf("invoke") !== -1 ||
                        methodName.indexOf("onText") !== -1 ||
                        methodName.indexOf("on") === 0) {

                        (function(mn, cls, pt) {
                            try {
                                if (pt.length === 1 && pt[0].getName() === "java.lang.String") {
                                    cls[mn].overload('java.lang.String').implementation = function(text) {
                                        console.log("\n<<< [" + mn + "] " + text.substring(0, 2000));
                                        return this[mn](text);
                                    };
                                    console.log("    -> Hooked with String param");
                                }
                            } catch(e) {}
                        })(methodName, cls, paramTypes);
                    }
                }
            } catch(e) {
                console.log("[-] " + className + ": " + e.message);
            }
        });

        // ============ Hook SocketEventParser ============
        try {
            var SocketEventParser = Java.use("com.avito.android.socketEvents.SocketEventParserByClass");
            console.log("\n[+] Found SocketEventParserByClass");

            var parserMethods = SocketEventParser.class.getDeclaredMethods();
            for (var i = 0; i < parserMethods.length; i++) {
                console.log("  Parser method: " + parserMethods[i].getName());
            }
        } catch(e) {
            console.log("[-] SocketEventParser: " + e.message);
        }

        // ============ Hook WebSocket send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");
            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> SEND: " + text.substring(0, 500));
                return this.send(text);
            };
            console.log("[+] RealWebSocket.send hooked");
        } catch(e) {}

        // ============ Hook WebSocketReader.readMessage ============
        try {
            var WebSocketReader = Java.use("okhttp3.internal.ws.WebSocketReader");
            var FrameCallback = Java.use("okhttp3.internal.ws.WebSocketReader$FrameCallback");

            console.log("\n[+] Checking WebSocketReader");

            // List FrameCallback methods
            try {
                var cbMethods = FrameCallback.class.getDeclaredMethods();
                for (var i = 0; i < cbMethods.length; i++) {
                    console.log("  FrameCallback: " + cbMethods[i].getName());
                }
            } catch(e) {}

        } catch(e) {
            console.log("[-] WebSocketReader: " + e.message);
        }

        // ============ Hook clientEventBus ============
        try {
            var eventBusClass = Java.use("com.avito.android.clientEventBus.repository.socketEvents.d$a");
            console.log("\n[+] Found clientEventBus socket class");

            var ebMethods = eventBusClass.class.getDeclaredMethods();
            for (var i = 0; i < ebMethods.length; i++) {
                var m = ebMethods[i];
                console.log("  EventBus: " + m.getName());
            }
        } catch(e) {}

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("\n[*] Ready! Open messages...\n");
    });
}, 1000);
