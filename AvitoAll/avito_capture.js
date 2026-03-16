// Avito Traffic Capture v1.0
// Full SSL bypass + detailed request/response logging for API analysis

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito Traffic Capture v1.0\n");

        // ============ SSL BYPASS ============

        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");
            try { CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {}; } catch(e) {}
            try { CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {}; } catch(e) {}
            try { CertificatePinner['check$okhttp'].implementation = function(a, b) {}; } catch(e) {}
        } catch(e) {}

        try {
            var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
            TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
                return untrustedChain;
            };
        } catch(e) {}

        try {
            var AvitoInterceptor = Java.use("com.avito.android.remote.interceptor.x");
            AvitoInterceptor.intercept.implementation = function(chain) {
                return chain.proceed(chain.request());
            };
        } catch(e) {}

        try {
            var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var SSLContext = Java.use('javax.net.ssl.SSLContext');
            var TrustManager = Java.registerClass({
                name: 'dev.avito.TrustAllCapture',
                implements: [X509TrustManager],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });
            var TrustManagers = [TrustManager.$new()];
            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                this.init(km, TrustManagers, sr);
            };
        } catch(e) {}

        console.log("[+] SSL Bypass active\n");

        // ============ DETAILED LOGGING ============

        // Helper to read request body
        function readRequestBody(body) {
            if (body === null) return null;
            try {
                var Buffer = Java.use("okio.Buffer");
                var buffer = Buffer.$new();
                body.writeTo(buffer);
                return buffer.readUtf8();
            } catch(e) {
                return "[body read error]";
            }
        }

        // Hook Interceptor chain to capture full requests
        try {
            var Interceptor = Java.use("okhttp3.Interceptor");
            var Chain = Java.use("okhttp3.Interceptor$Chain");

            // Find RealInterceptorChain
            var RealInterceptorChain = null;
            try {
                RealInterceptorChain = Java.use("okhttp3.internal.http.RealInterceptorChain");
            } catch(e) {
                try {
                    RealInterceptorChain = Java.use("okhttp3.RealInterceptorChain");
                } catch(e2) {}
            }

            if (RealInterceptorChain) {
                RealInterceptorChain.proceed.overload('okhttp3.Request').implementation = function(request) {
                    var url = request.url().toString();

                    // Only log Avito API requests
                    if (url.indexOf("avito.ru") !== -1) {
                        console.log("\n========== REQUEST ==========");
                        console.log("[URL] " + url);
                        console.log("[Method] " + request.method());

                        // Log ALL headers
                        var headers = request.headers();
                        var size = headers.size();
                        console.log("[Headers]");
                        for (var i = 0; i < size; i++) {
                            console.log("  " + headers.name(i) + ": " + headers.value(i));
                        }

                        // Log body for POST/PUT
                        var body = request.body();
                        if (body !== null) {
                            console.log("[Body Type] " + body.contentType());
                            var bodyContent = readRequestBody(body);
                            if (bodyContent && bodyContent.length < 2000) {
                                console.log("[Body] " + bodyContent);
                            } else if (bodyContent) {
                                console.log("[Body] (truncated) " + bodyContent.substring(0, 500) + "...");
                            }
                        }
                    }

                    // Execute request
                    var response = this.proceed(request);

                    // Log response for Avito
                    if (url.indexOf("avito.ru") !== -1) {
                        console.log("\n---------- RESPONSE ----------");
                        console.log("[Code] " + response.code());

                        // Log response headers
                        var respHeaders = response.headers();
                        var respSize = respHeaders.size();
                        console.log("[Response Headers]");
                        for (var j = 0; j < respSize; j++) {
                            console.log("  " + respHeaders.name(j) + ": " + respHeaders.value(j));
                        }

                        // Try to peek response body
                        try {
                            var bodyStr = response.peekBody(Java.use("java.lang.Long").parseLong("10240")).string();
                            if (bodyStr.length < 2000) {
                                console.log("[Response Body] " + bodyStr);
                            } else {
                                console.log("[Response Body] (truncated) " + bodyStr.substring(0, 500) + "...");
                            }
                        } catch(e) {}

                        console.log("==============================\n");
                    }

                    return response;
                };
                console.log("[+] Request/Response logging enabled");
            }
        } catch(e) {
            console.log("[-] Interceptor hook failed: " + e);
        }

        // Also hook Request.Builder.addHeader to catch header generation
        try {
            var RequestBuilder = Java.use("okhttp3.Request$Builder");

            RequestBuilder.addHeader.implementation = function(name, value) {
                // Log interesting headers
                if (name.toString().startsWith("X-") ||
                    name.toString().toLowerCase().indexOf("auth") !== -1 ||
                    name.toString().toLowerCase().indexOf("token") !== -1 ||
                    name.toString().toLowerCase().indexOf("sign") !== -1 ||
                    name.toString().toLowerCase().indexOf("session") !== -1) {
                    console.log("[HEADER ADD] " + name + ": " + value);
                }
                return this.addHeader(name, value);
            };

            RequestBuilder.header.implementation = function(name, value) {
                if (name.toString().startsWith("X-") ||
                    name.toString().toLowerCase().indexOf("auth") !== -1 ||
                    name.toString().toLowerCase().indexOf("token") !== -1 ||
                    name.toString().toLowerCase().indexOf("sign") !== -1 ||
                    name.toString().toLowerCase().indexOf("session") !== -1) {
                    console.log("[HEADER SET] " + name + ": " + value);
                }
                return this.header(name, value);
            };

            console.log("[+] Header generation logging enabled");
        } catch(e) {
            console.log("[-] Header hook: " + e);
        }

        // Hook SharedPreferences to find stored tokens
        try {
            var SharedPreferencesImpl = Java.use("android.app.SharedPreferencesImpl");
            SharedPreferencesImpl.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
                var result = this.getString(key, defValue);
                if (key.toLowerCase().indexOf("token") !== -1 ||
                    key.toLowerCase().indexOf("session") !== -1 ||
                    key.toLowerCase().indexOf("auth") !== -1 ||
                    key.toLowerCase().indexOf("user") !== -1) {
                    console.log("[PREF] " + key + " = " + result);
                }
                return result;
            };
            console.log("[+] SharedPreferences monitoring enabled");
        } catch(e) {}

        console.log("\n[*] Traffic Capture ready! Use the app to see requests.\n");
    });
}, 2000);
