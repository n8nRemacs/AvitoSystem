/*
 * HTTP Headers Capture v2
 * Captures headers at CallServerInterceptor level (final before network)
 */

Java.perform(function() {
    console.log("[*] Headers Capture v2 loaded");

    // Method 1: Hook CallServerInterceptor.intercept
    try {
        var CallServerInterceptor = Java.use('okhttp3.internal.http.CallServerInterceptor');

        CallServerInterceptor.intercept.implementation = function(chain) {
            var request = chain.request();
            var url = request.url().toString();

            // Only detailed log for auth endpoints
            if (url.includes("/api/11/auth") || url.includes("/api/1/auth") || url.includes("auth")) {
                console.log("\n" + "#".repeat(70));
                console.log("[CALLSERVER] FINAL REQUEST BEFORE NETWORK");
                console.log("[URL] " + request.method() + " " + url);
                console.log("#".repeat(70));

                // Print ALL headers at this point
                var headers = request.headers();
                var headerCount = headers.size();
                console.log("\n[HEADERS] Total count: " + headerCount);

                for (var i = 0; i < headerCount; i++) {
                    var name = headers.name(i);
                    var value = headers.value(i);
                    // Don't mask headers - we need to see everything
                    console.log("  " + name + ": " + value);
                }

                // Print body if exists
                var body = request.body();
                if (body != null) {
                    console.log("\n[BODY INFO]");
                    console.log("  Content-Type: " + body.contentType());
                    console.log("  Content-Length: " + body.contentLength());

                    try {
                        var okioBuffer = Java.use('okio.Buffer');
                        var buffer = okioBuffer.$new();
                        body.writeTo(buffer);
                        var bodyContent = buffer.readUtf8();
                        // Mask password for security
                        var maskedBody = bodyContent.replace(/password=[^&]+/, "password=***");
                        console.log("  Content: " + maskedBody);
                    } catch(e) {
                        console.log("  Body read error: " + e);
                    }
                }

                console.log("\n" + "#".repeat(70));
            }

            return this.intercept(chain);
        };

        console.log("[+] CallServerInterceptor.intercept hooked");
    } catch(e) {
        console.log("[-] CallServerInterceptor error: " + e);
    }

    // Method 2: Hook BridgeInterceptor to see headers after standard headers added
    try {
        var BridgeInterceptor = Java.use('okhttp3.internal.http.BridgeInterceptor');

        BridgeInterceptor.intercept.implementation = function(chain) {
            var request = chain.request();
            var url = request.url().toString();

            if (url.includes("/api/") && url.includes("auth")) {
                console.log("\n[BRIDGE INTERCEPTOR] Processing auth request");
                console.log("[URL] " + url);

                var headers = request.headers();
                console.log("[HEADERS BEFORE BRIDGE] Count: " + headers.size());
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

    // Method 3: Hook Request.Builder.build to see final request being constructed
    try {
        var RequestBuilder = Java.use('okhttp3.Request$Builder');

        RequestBuilder.build.implementation = function() {
            var request = this.build();
            var url = request.url().toString();

            if (url.includes("/api/11/auth") || url.includes("/api/1/auth")) {
                console.log("\n[REQUEST.BUILDER] Built request for: " + url);
                var headers = request.headers();
                console.log("[BUILT HEADERS] Count: " + headers.size());
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }

            return request;
        };

        console.log("[+] Request.Builder.build hooked");
    } catch(e) {
        console.log("[-] Request.Builder error: " + e);
    }

    // Method 4: Hook each known interceptor to see what headers they add
    var interceptorClasses = [
        'com.avito.android.remote.interceptor.Z0',  // UserAgent
        'com.avito.android.remote.interceptor.f',   // AcceptLanguage (renamed class)
        'com.avito.android.remote.interceptor.O0',  // SupportedFeatures
        'com.avito.android.remote.interceptor.g0',  // Headers
        'com.avito.android.remote.interceptor.A',   // Date
    ];

    interceptorClasses.forEach(function(className) {
        try {
            var InterceptorClass = Java.use(className);
            InterceptorClass.intercept.implementation = function(chain) {
                var request = chain.request();
                var url = request.url().toString();

                if (url.includes("auth")) {
                    console.log("\n[" + className.split('.').pop() + "] Processing: " + url);
                    var headers = request.headers();
                    console.log("  Headers IN: " + headers.size());
                }

                var response = this.intercept(chain);
                return response;
            };
            console.log("[+] " + className + " hooked");
        } catch(e) {
            // Silently skip if class not found
        }
    });

    console.log("\n[*] Headers Capture v2 READY!");
    console.log("[*] Log out of Avito and log in again to capture auth headers\n");
});
