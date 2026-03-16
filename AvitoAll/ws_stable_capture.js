// Stable WebSocket capture - both directions
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Stable WebSocket Capture\n");

        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            // Outgoing
            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                try {
                    var j = JSON.parse(text);
                    console.log("\n>>> OUT [" + (j.method || "response") + "] id=" + j.id);
                    if (j.params) console.log("    params: " + JSON.stringify(j.params).substring(0, 200));
                } catch(e) {
                    console.log("\n>>> OUT: " + text.substring(0, 200));
                }
                return this.send(text);
            };

            // Incoming
            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                try {
                    var j = JSON.parse(text);

                    // Check for push events (no "id" = server push)
                    if (!j.id && j.type) {
                        console.log("\n╔════════════════════════════════════════════");
                        console.log("║ PUSH EVENT: " + j.type);
                        console.log("╠════════════════════════════════════════════");
                        console.log("║ " + text.replace(/\n/g, "\n║ "));
                        console.log("╚════════════════════════════════════════════\n");
                    }
                    // Check for message events
                    else if (j.result && (j.result.messages || j.result.chats || j.result.channels)) {
                        console.log("\n<<< IN [result] id=" + j.id);
                        console.log("    " + text.substring(0, 500));
                    }
                    // Regular response
                    else if (j.id) {
                        console.log("\n<<< IN [resp] id=" + j.id);
                        if (text.length < 300) console.log("    " + text);
                    }
                    // Unknown format - log full
                    else {
                        console.log("\n<<< IN [???]");
                        console.log("    " + text.substring(0, 1000));
                    }
                } catch(e) {
                    console.log("\n<<< IN (raw): " + text.substring(0, 500));
                }
                return this.onReadMessage(text);
            };

            console.log("[+] WebSocket hooks active");
        } catch(e) {
            console.log("[-] Hook error: " + e);
        }

        // SSL bypass
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("[*] Ready! Open Avito messages and send/receive...\n");
    });
}, 1000);
