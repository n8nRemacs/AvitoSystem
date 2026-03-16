// Avito Messenger API Capture
// Captures all messenger-related HTTP traffic

setTimeout(function() {
    Java.perform(function() {
        console.log("\n========================================");
        console.log("[*] Avito Messenger API Capture v1.0");
        console.log("========================================\n");

        // ============ OkHttp3 Interceptor ============
        try {
            var OkHttpClient = Java.use("okhttp3.OkHttpClient");
            var Interceptor = Java.use("okhttp3.Interceptor");
            var Buffer = Java.use("okio.Buffer");

            // Hook Response
            var RealCall = Java.use("okhttp3.internal.connection.RealCall");

            RealCall.getResponseWithInterceptorChain.implementation = function() {
                var response = this.getResponseWithInterceptorChain();

                try {
                    var request = response.request();
                    var url = request.url().toString();
                    var method = request.method();

                    // Filter messenger-related URLs
                    if (url.indexOf("messenger") !== -1 ||
                        url.indexOf("socket") !== -1 ||
                        url.indexOf("channel") !== -1 ||
                        url.indexOf("chat") !== -1 ||
                        url.indexOf("message") !== -1) {

                        console.log("\n╔══════════════════════════════════════════════");
                        console.log("║ [" + method + "] " + url);
                        console.log("╠══════════════════════════════════════════════");

                        // Request Headers
                        var reqHeaders = request.headers();
                        console.log("║ REQUEST HEADERS:");
                        for (var i = 0; i < reqHeaders.size(); i++) {
                            var name = reqHeaders.name(i);
                            var value = reqHeaders.value(i);
                            // Truncate long values
                            if (value.length > 100) value = value.substring(0, 100) + "...";
                            console.log("║   " + name + ": " + value);
                        }

                        // Request Body
                        var reqBody = request.body();
                        if (reqBody) {
                            try {
                                var buffer = Buffer.$new();
                                reqBody.writeTo(buffer);
                                var bodyStr = buffer.readUtf8();
                                if (bodyStr.length > 0) {
                                    console.log("║ REQUEST BODY:");
                                    // Pretty print JSON
                                    try {
                                        var json = JSON.parse(bodyStr);
                                        console.log("║   " + JSON.stringify(json, null, 2).replace(/\n/g, "\n║   "));
                                    } catch(e) {
                                        console.log("║   " + bodyStr.substring(0, 500));
                                    }
                                }
                            } catch(e) {}
                        }

                        // Response
                        console.log("╠══════════════════════════════════════════════");
                        console.log("║ RESPONSE: " + response.code() + " " + response.message());

                        // Response Headers
                        var respHeaders = response.headers();
                        console.log("║ RESPONSE HEADERS:");
                        for (var i = 0; i < respHeaders.size(); i++) {
                            var name = respHeaders.name(i);
                            var value = respHeaders.value(i);
                            if (value.length > 100) value = value.substring(0, 100) + "...";
                            console.log("║   " + name + ": " + value);
                        }

                        // Response Body (need to peek)
                        try {
                            var responseBody = response.peekBody(1024 * 100); // 100KB max
                            var bodyStr = responseBody.string();
                            if (bodyStr.length > 0) {
                                console.log("║ RESPONSE BODY:");
                                try {
                                    var json = JSON.parse(bodyStr);
                                    var formatted = JSON.stringify(json, null, 2);
                                    if (formatted.length > 2000) {
                                        formatted = formatted.substring(0, 2000) + "\n... (truncated)";
                                    }
                                    console.log("║   " + formatted.replace(/\n/g, "\n║   "));
                                } catch(e) {
                                    console.log("║   " + bodyStr.substring(0, 1000));
                                }
                            }
                        } catch(e) {}

                        console.log("╚══════════════════════════════════════════════\n");
                    }
                } catch(e) {
                    // Silently ignore errors
                }

                return response;
            };

            console.log("[+] OkHttp RealCall hooked");
        } catch(e) {
            console.log("[-] OkHttp hook error: " + e);
        }

        // ============ WebSocket Messages ============
        try {
            var WebSocketListener = Java.use("okhttp3.WebSocketListener");

            WebSocketListener.onMessage.overload('okhttp3.WebSocket', 'java.lang.String').implementation = function(ws, text) {
                try {
                    var json = JSON.parse(text);

                    // Filter interesting message types
                    var type = json.type || json.method || "";
                    if (type.indexOf("message") !== -1 ||
                        type.indexOf("channel") !== -1 ||
                        type.indexOf("typing") !== -1 ||
                        type.indexOf("read") !== -1 ||
                        type === "result" ||
                        json.params) {

                        console.log("\n┌─────────────────────────────────────────────");
                        console.log("│ [WS RECEIVE] " + type);
                        console.log("├─────────────────────────────────────────────");
                        var formatted = JSON.stringify(json, null, 2);
                        if (formatted.length > 3000) {
                            formatted = formatted.substring(0, 3000) + "\n... (truncated)";
                        }
                        console.log("│ " + formatted.replace(/\n/g, "\n│ "));
                        console.log("└─────────────────────────────────────────────\n");
                    }
                } catch(e) {
                    if (text.length < 500) {
                        console.log("[WS RAW] " + text);
                    }
                }

                return this.onMessage(ws, text);
            };

            console.log("[+] WebSocket onMessage hooked");
        } catch(e) {
            console.log("[-] WebSocket hook error: " + e);
        }

        // ============ WebSocket Send ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                try {
                    var json = JSON.parse(text);
                    console.log("\n┌─────────────────────────────────────────────");
                    console.log("│ [WS SEND] " + (json.method || json.type || ""));
                    console.log("├─────────────────────────────────────────────");
                    var formatted = JSON.stringify(json, null, 2);
                    if (formatted.length > 2000) {
                        formatted = formatted.substring(0, 2000) + "\n... (truncated)";
                    }
                    console.log("│ " + formatted.replace(/\n/g, "\n│ "));
                    console.log("└─────────────────────────────────────────────\n");
                } catch(e) {
                    console.log("[WS SEND RAW] " + text.substring(0, 500));
                }

                return this.send(text);
            };

            console.log("[+] WebSocket send hooked");
        } catch(e) {
            console.log("[-] WebSocket send hook error: " + e);
        }

        // ============ SSL Bypass (for MITM if needed) ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
            console.log("[+] SSL bypass active");
        } catch(e) {}

        try {
            var CertificatePinner = Java.use('okhttp3.CertificatePinner');
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function() {
                return;
            };
            console.log("[+] OkHttp CertificatePinner bypassed");
        } catch(e) {}

        console.log("\n[*] Ready! Navigate to messages in Avito app...\n");
    });
}, 1000);
