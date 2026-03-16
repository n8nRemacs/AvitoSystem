// Full Authentication Flow Capture
// Captures: phone input, captcha, SMS, TFA
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Full Auth Flow Capture\n");

        // ============ HTTP Requests/Responses ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> WS: " + text.substring(0, 300));
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                console.log("\n<<< WS: " + text.substring(0, 500));
                return this.onReadMessage(text);
            };
            console.log("[+] WebSocket hooked");
        } catch(e) {}

        // ============ OkHttp Interceptor for HTTP ============
        try {
            var OkHttpClient = Java.use("okhttp3.OkHttpClient");
            var Request = Java.use("okhttp3.Request");
            var RequestBody = Java.use("okhttp3.RequestBody");

            // Hook the newCall to intercept requests
            var RealCall = Java.use("okhttp3.RealCall");

            RealCall.execute.implementation = function() {
                var request = this.request();
                var url = request.url().toString();
                var method = request.method();

                // Log auth-related requests
                if (url.indexOf("auth") !== -1 ||
                    url.indexOf("captcha") !== -1 ||
                    url.indexOf("tfa") !== -1 ||
                    url.indexOf("sms") !== -1 ||
                    url.indexOf("phone") !== -1 ||
                    url.indexOf("login") !== -1 ||
                    url.indexOf("session") !== -1 ||
                    url.indexOf("code") !== -1) {

                    console.log("\n╔════════════════════════════════════════════════════");
                    console.log("║ [HTTP " + method + "] " + url);
                    console.log("╠════════════════════════════════════════════════════");

                    // Headers
                    var headers = request.headers();
                    for (var i = 0; i < headers.size(); i++) {
                        var name = headers.name(i);
                        var value = headers.value(i);
                        if (name.toLowerCase().indexOf("cookie") !== -1 ||
                            name.toLowerCase().indexOf("session") !== -1 ||
                            name.toLowerCase().indexOf("auth") !== -1 ||
                            name.toLowerCase().indexOf("device") !== -1 ||
                            name.toLowerCase().indexOf("x-") === 0) {
                            console.log("║ " + name + ": " + value.substring(0, 100));
                        }
                    }

                    // Body
                    var body = request.body();
                    if (body) {
                        try {
                            var Buffer = Java.use("okio.Buffer");
                            var buffer = Buffer.$new();
                            body.writeTo(buffer);
                            var bodyStr = buffer.readUtf8();
                            console.log("║ BODY: " + bodyStr.substring(0, 500));
                        } catch(e) {}
                    }
                }

                var response = this.execute();

                // Log response for auth requests
                if (url.indexOf("auth") !== -1 ||
                    url.indexOf("captcha") !== -1 ||
                    url.indexOf("tfa") !== -1) {

                    console.log("╠════════════════════════════════════════════════════");
                    console.log("║ RESPONSE: " + response.code());

                    try {
                        var responseBody = response.peekBody(50000);
                        var respStr = responseBody.string();
                        console.log("║ " + respStr.substring(0, 1500));
                    } catch(e) {}

                    console.log("╚════════════════════════════════════════════════════\n");
                }

                return response;
            };

            console.log("[+] OkHttp execute hooked");
        } catch(e) {
            console.log("[-] OkHttp error: " + e);
        }

        // ============ Async HTTP (enqueue) ============
        try {
            var RealCall = Java.use("okhttp3.RealCall");

            RealCall.enqueue.implementation = function(callback) {
                var request = this.request();
                var url = request.url().toString();
                var method = request.method();

                if (url.indexOf("auth") !== -1 ||
                    url.indexOf("captcha") !== -1 ||
                    url.indexOf("tfa") !== -1 ||
                    url.indexOf("sms") !== -1 ||
                    url.indexOf("phone") !== -1 ||
                    url.indexOf("login") !== -1) {

                    console.log("\n┌────────────────────────────────────────────────────");
                    console.log("│ [ASYNC " + method + "] " + url);

                    var body = request.body();
                    if (body) {
                        try {
                            var Buffer = Java.use("okio.Buffer");
                            var buffer = Buffer.$new();
                            body.writeTo(buffer);
                            var bodyStr = buffer.readUtf8();
                            console.log("│ BODY: " + bodyStr.substring(0, 500));
                        } catch(e) {}
                    }
                    console.log("└────────────────────────────────────────────────────\n");
                }

                return this.enqueue(callback);
            };

            console.log("[+] OkHttp enqueue hooked");
        } catch(e) {
            console.log("[-] Enqueue error: " + e);
        }

        // ============ Captcha related classes ============
        try {
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.toLowerCase().indexOf("captcha") !== -1 ||
                        className.toLowerCase().indexOf("slider") !== -1 ||
                        className.toLowerCase().indexOf("puzzle") !== -1) {
                        console.log("[CAPTCHA CLASS] " + className);
                    }
                },
                onComplete: function() {}
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

        try {
            var CertificatePinner = Java.use('okhttp3.CertificatePinner');
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function() {
                return;
            };
        } catch(e) {}

        console.log("\n[*] Ready! Now logout and try to login again...\n");
    });
}, 1000);
