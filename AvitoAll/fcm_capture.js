// Firebase Cloud Messaging (FCM) + WebSocket capture
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] FCM + WebSocket Capture\n");

        // ============ FCM FirebaseMessagingService ============
        try {
            var FirebaseMessagingService = Java.use("com.google.firebase.messaging.FirebaseMessagingService");

            FirebaseMessagingService.onMessageReceived.implementation = function(remoteMessage) {
                console.log("\n╔══════════════════════════════════════════════════");
                console.log("║ [FCM] MESSAGE RECEIVED!");
                console.log("╠══════════════════════════════════════════════════");

                try {
                    // Get notification data
                    var data = remoteMessage.getData();
                    console.log("║ Data: " + data.toString());

                    var notification = remoteMessage.getNotification();
                    if (notification) {
                        console.log("║ Title: " + notification.getTitle());
                        console.log("║ Body: " + notification.getBody());
                    }

                    console.log("║ From: " + remoteMessage.getFrom());
                    console.log("║ MessageId: " + remoteMessage.getMessageId());
                } catch(e) {
                    console.log("║ Error getting data: " + e);
                }

                console.log("╚══════════════════════════════════════════════════\n");
                return this.onMessageReceived(remoteMessage);
            };

            console.log("[+] FirebaseMessagingService.onMessageReceived hooked");
        } catch(e) {
            console.log("[-] FCM hook error: " + e);
        }

        // ============ Avito's FCM Service ============
        try {
            // Search for Avito push service
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf("avito") !== -1 &&
                        (className.indexOf("Firebase") !== -1 ||
                         className.indexOf("firebase") !== -1 ||
                         className.indexOf("Push") !== -1 ||
                         className.indexOf("push") !== -1 ||
                         className.indexOf("Messaging") !== -1)) {
                        console.log("[PUSH CLASS] " + className);
                    }
                },
                onComplete: function() {}
            });
        } catch(e) {}

        // ============ WebSocket ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                var j = JSON.parse(text);
                console.log(">>> WS OUT [" + (j.method || "") + "]");
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                try {
                    var j = JSON.parse(text);

                    // Push events without id
                    if (!j.id || j.type) {
                        console.log("\n┌─────────────────────────────────────────────");
                        console.log("│ WS PUSH: " + (j.type || "unknown"));
                        console.log("├─────────────────────────────────────────────");
                        console.log("│ " + text.replace(/\n/g, "\n│ ").substring(0, 2000));
                        console.log("└─────────────────────────────────────────────\n");
                    } else {
                        console.log("<<< WS IN [resp] id=" + j.id);
                    }
                } catch(e) {
                    console.log("<<< WS IN (raw): " + text.substring(0, 500));
                }
                return this.onReadMessage(text);
            };

            console.log("[+] WebSocket hooked");
        } catch(e) {
            console.log("[-] WS error: " + e);
        }

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
        } catch(e) {}

        console.log("\n[*] Ready! Waiting for push notifications...\n");
    });
}, 1000);
