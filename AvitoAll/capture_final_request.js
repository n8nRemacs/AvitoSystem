/*
 * Capture FINAL HTTP Request (after all interceptors)
 * Hooks at network level to see actual headers sent
 */

Java.perform(function() {
    console.log("[*] Final Request Capture loaded");
    console.log("[*] Will capture headers AFTER all interceptors process them\n");

    // Hook RealInterceptorChain.proceed - this is called at each step of the chain
    try {
        var RealInterceptorChain = Java.use('okhttp3.internal.http.RealInterceptorChain');

        RealInterceptorChain.proceed.overload('okhttp3.Request').implementation = function(request) {
            var url = request.url().toString();

            // Only log for auth endpoints
            if (url.includes("/api/11/auth") || url.includes("/api/1/visitor") || url.includes("/api/1/auth")) {
                // Get current interceptor index
                var index = this.index$okhttp.value;
                var interceptors = this.interceptors$okhttp.value;
                var totalInterceptors = interceptors.size();

                // Log only at the LAST interceptor (network level)
                if (index >= totalInterceptors - 2) {
                    console.log("\n" + "=".repeat(70));
                    console.log("[FINAL REQUEST] Index " + index + "/" + totalInterceptors);
                    console.log("[URL] " + request.method() + " " + url);
                    console.log("=".repeat(70));

                    // Print ALL final headers
                    var headers = request.headers();
                    console.log("\n[FINAL HEADERS] Count: " + headers.size());
                    for (var i = 0; i < headers.size(); i++) {
                        var name = headers.name(i);
                        var value = headers.value(i);
                        // Mask sensitive values
                        if (name.toLowerCase().includes("auth") || name.toLowerCase().includes("token") || name.toLowerCase().includes("secret")) {
                            console.log("  " + name + ": " + value.substring(0, 20) + "...[MASKED]");
                        } else {
                            console.log("  " + name + ": " + value);
                        }
                    }

                    // Print body
                    var body = request.body();
                    if (body != null) {
                        try {
                            var Buffer = Java.use('okio.Buffer');
                            var buffer = Buffer.$new();
                            body.writeTo(buffer);
                            var bodyStr = buffer.readUtf8();
                            console.log("\n[BODY] Length: " + bodyStr.length);
                            // Mask password in body
                            var maskedBody = bodyStr.replace(/password=[^&]+/, "password=***MASKED***");
                            console.log("[BODY] " + maskedBody);
                        } catch(e) {
                            console.log("[BODY] Error: " + e);
                        }
                    }
                    console.log("\n" + "=".repeat(70) + "\n");
                }
            }

            return this.proceed(request);
        };

        console.log("[+] RealInterceptorChain.proceed hooked");
    } catch(e) {
        console.log("[-] RealInterceptorChain error: " + e);
    }

    // Alternative: Hook BridgeInterceptor which adds standard headers
    try {
        var BridgeInterceptor = Java.use('okhttp3.internal.http.BridgeInterceptor');

        BridgeInterceptor.intercept.implementation = function(chain) {
            var request = chain.request();
            var url = request.url().toString();

            if (url.includes("/api/11/auth")) {
                console.log("\n[BridgeInterceptor] Processing: " + url);
                console.log("[BridgeInterceptor] Headers before bridge:");
                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }

            var response = this.intercept(chain);
            return response;
        };

        console.log("[+] BridgeInterceptor hooked");
    } catch(e) {
        console.log("[-] BridgeInterceptor error: " + e);
    }

    // Hook CallServerInterceptor - the LAST interceptor that actually sends request
    try {
        var CallServerInterceptor = Java.use('okhttp3.internal.http.CallServerInterceptor');

        CallServerInterceptor.intercept.implementation = function(chain) {
            var request = chain.request();
            var url = request.url().toString();

            if (url.includes("/api/11/auth") || url.includes("/api/1/auth")) {
                console.log("\n" + "#".repeat(70));
                console.log("[CallServerInterceptor] FINAL REQUEST TO SERVER");
                console.log("[URL] " + request.method() + " " + url);
                console.log("#".repeat(70));

                var headers = request.headers();
                console.log("\n[HEADERS SENT TO SERVER] Count: " + headers.size());
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
                console.log("#".repeat(70) + "\n");
            }

            return this.intercept(chain);
        };

        console.log("[+] CallServerInterceptor hooked");
    } catch(e) {
        console.log("[-] CallServerInterceptor error: " + e);
    }

    // Hook Http2ExchangeCodec or Http1ExchangeCodec for raw wire data
    try {
        var Http2ExchangeCodec = Java.use('okhttp3.internal.http2.Http2ExchangeCodec');

        Http2ExchangeCodec.writeRequestHeaders.implementation = function(request) {
            var url = request.url().toString();

            if (url.includes("/api/") && url.includes("auth")) {
                console.log("\n[HTTP2 WIRE] Writing headers for: " + url);
                var headers = request.headers();
                console.log("[HTTP2 WIRE] Header count: " + headers.size());
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }

            return this.writeRequestHeaders(request);
        };

        console.log("[+] Http2ExchangeCodec hooked");
    } catch(e) {
        console.log("[-] Http2ExchangeCodec: " + e);
    }

    console.log("\n[*] Final Request Capture READY!");
    console.log("[*] Login to Avito to see REAL headers sent to server\n");
});
