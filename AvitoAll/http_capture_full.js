/*
 * Full HTTP Headers Capture
 * Captures ALL request/response headers and body for auth endpoint
 */

Java.perform(function() {
    console.log("[*] Full HTTP Capture loaded");
    console.log("[*] Will capture ALL headers for /api/11/auth");

    // Hook OkHttp3 RealCall.execute()
    try {
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');

        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();
            var method = request.method();

            // Only detailed log for auth endpoint
            if (url.includes("/api/11/auth") || url.includes("/api/1/visitor") || url.includes("/api/1/auth")) {
                console.log("\n" + "=".repeat(60));
                console.log("[REQUEST] " + method + " " + url);
                console.log("=".repeat(60));

                // Print ALL headers
                var headers = request.headers();
                console.log("\n[HEADERS] Count: " + headers.size());
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }

                // Print body
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use('okio.Buffer');
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var contentType = body.contentType();
                        console.log("\n[BODY] Content-Type: " + contentType);
                        console.log("[BODY] Content-Length: " + body.contentLength());

                        var bodyStr = buffer.readUtf8();
                        if (bodyStr.length < 10000) {
                            console.log("[BODY] Content:\n" + bodyStr);
                        } else {
                            console.log("[BODY] (too large: " + bodyStr.length + " chars)");
                        }
                    } catch(e) {
                        console.log("[BODY] Error reading: " + e);
                    }
                }

                // Execute request
                var response = this.execute();

                console.log("\n" + "-".repeat(60));
                console.log("[RESPONSE] " + response.code() + " " + response.message());
                console.log("-".repeat(60));

                // Print response headers
                var respHeaders = response.headers();
                console.log("\n[RESP HEADERS] Count: " + respHeaders.size());
                for (var i = 0; i < respHeaders.size(); i++) {
                    console.log("  " + respHeaders.name(i) + ": " + respHeaders.value(i));
                }

                // Print response body
                try {
                    var respBody = response.peekBody(Java.use('java.lang.Long').MAX_VALUE.value);
                    var respStr = respBody.string();
                    console.log("\n[RESP BODY] Length: " + respStr.length);
                    if (respStr.length < 5000) {
                        console.log("[RESP BODY] Content:\n" + respStr);
                    }
                } catch(e) {
                    console.log("[RESP BODY] Error: " + e);
                }

                console.log("\n" + "=".repeat(60) + "\n");

                return response;
            }

            // For other URLs, just execute normally
            return this.execute();
        };

        console.log("[+] RealCall.execute hooked");
    } catch(e) {
        console.log("[-] RealCall.execute error: " + e);
    }

    // Also hook async calls
    try {
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');

        RealCall.enqueue.implementation = function(callback) {
            var request = this.request();
            var url = request.url().toString();
            var method = request.method();

            if (url.includes("/api/11/auth") || url.includes("/api/1/visitor") || url.includes("/api/1/auth")) {
                console.log("\n" + "=".repeat(60));
                console.log("[ASYNC REQUEST] " + method + " " + url);
                console.log("=".repeat(60));

                // Print ALL headers
                var headers = request.headers();
                console.log("\n[HEADERS] Count: " + headers.size());
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }

                // Print body
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use('okio.Buffer');
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var contentType = body.contentType();
                        console.log("\n[BODY] Content-Type: " + contentType);

                        var bodyStr = buffer.readUtf8();
                        if (bodyStr.length < 10000) {
                            console.log("[BODY] Content:\n" + bodyStr);
                        }
                    } catch(e) {
                        console.log("[BODY] Error: " + e);
                    }
                }

                console.log("=".repeat(60) + "\n");
            }

            return this.enqueue(callback);
        };

        console.log("[+] RealCall.enqueue hooked");
    } catch(e) {
        console.log("[-] RealCall.enqueue error: " + e);
    }

    // Hook OkHttpClient.Builder to see all interceptors
    try {
        var OkHttpClientBuilder = Java.use('okhttp3.OkHttpClient$Builder');

        OkHttpClientBuilder.build.implementation = function() {
            var client = this.build();

            // Log interceptors
            var interceptors = client.interceptors();
            console.log("\n[OkHttpClient] Interceptors count: " + interceptors.size());
            for (var i = 0; i < interceptors.size(); i++) {
                console.log("  [" + i + "] " + interceptors.get(i).getClass().getName());
            }

            var networkInterceptors = client.networkInterceptors();
            console.log("[OkHttpClient] Network interceptors count: " + networkInterceptors.size());
            for (var i = 0; i < networkInterceptors.size(); i++) {
                console.log("  [" + i + "] " + networkInterceptors.get(i).getClass().getName());
            }

            return client;
        };

        console.log("[+] OkHttpClient.Builder.build hooked");
    } catch(e) {
        console.log("[-] OkHttpClient.Builder: " + e);
    }

    console.log("\n[*] Full HTTP Capture READY!");
    console.log("[*] Now login to Avito - all auth headers will be captured");
    console.log("[*] Look for /api/11/auth requests\n");
});
