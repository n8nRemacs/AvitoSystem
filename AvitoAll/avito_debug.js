// Avito SSL Killer v4.0 - Debug version with response logging
// Logs both requests and responses to diagnose connectivity issues

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito SSL Killer v4.0 - DEBUG MODE\n");

        // ============ SSL BYPASS ============

        // 1. Kill OkHttp CertificatePinner
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");

            try {
                CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {
                    console.log("[SSL] CertificatePinner.check killed: " + a);
                    return; // void method
                };
            } catch(e) {}

            try {
                CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {
                    console.log("[SSL] CertificatePinner.check killed: " + a);
                    return;
                };
            } catch(e) {}

            try {
                CertificatePinner['check$okhttp'].implementation = function(a, b) {
                    console.log("[SSL] check$okhttp killed: " + a);
                    return;
                };
            } catch(e) {}

            console.log("[+] CertificatePinner neutralized");
        } catch(e) {
            console.log("[-] CertificatePinner: " + e);
        }

        // 2. Kill TrustManagerImpl
        try {
            var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
            TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
                console.log("[SSL] verifyChain bypassed: " + host);
                return untrustedChain;
            };
            console.log("[+] TrustManagerImpl.verifyChain patched");
        } catch(e) {
            console.log("[-] verifyChain: " + e);
        }

        // 3. Kill Avito interceptor
        try {
            var AvitoInterceptor = Java.use("com.avito.android.remote.interceptor.x");
            AvitoInterceptor.intercept.implementation = function(chain) {
                var req = chain.request();
                var url = req.url().toString();
                console.log("[AVITO] Interceptor bypassed: " + url);
                return chain.proceed(req);
            };
            console.log("[+] Avito interceptor hooked");
        } catch(e) {
            console.log("[-] Avito interceptor: " + e);
        }

        // 4. Patch SSLContext
        try {
            var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var SSLContext = Java.use('javax.net.ssl.SSLContext');

            var TrustManager = Java.registerClass({
                name: 'dev.avito.TrustAllX509Debug',
                implements: [X509TrustManager],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });

            var TrustManagers = [TrustManager.$new()];

            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                console.log("[SSL] SSLContext.init hijacked");
                this.init(km, TrustManagers, sr);
            };
            console.log("[+] SSLContext patched");
        } catch(e) {
            console.log("[-] SSLContext: " + e);
        }

        // ============ REQUEST/RESPONSE LOGGING ============

        // 5. Log ALL OkHttp requests and responses
        try {
            var RealCall = Java.use("okhttp3.RealCall");

            RealCall.execute.implementation = function() {
                var request = this.request();
                var url = request.url().toString();
                var method = request.method();

                console.log("\n[REQ] " + method + " " + url);

                // Log headers
                var headers = request.headers();
                var size = headers.size();
                for (var i = 0; i < size; i++) {
                    var name = headers.name(i);
                    if (name.startsWith("X-") || name.toLowerCase().indexOf("auth") !== -1 || name.toLowerCase().indexOf("cookie") !== -1) {
                        console.log("  [H] " + name + ": " + headers.value(i).substring(0, 100));
                    }
                }

                try {
                    var response = this.execute();
                    var code = response.code();
                    console.log("[RES] " + code + " " + url.substring(0, 80));

                    if (code >= 400) {
                        console.log("[!] ERROR RESPONSE: " + code);
                        try {
                            var body = response.peekBody(Java.use("java.lang.Long").parseLong("1024")).string();
                            console.log("[!] Body: " + body.substring(0, 200));
                        } catch(e) {}
                    }

                    return response;
                } catch(e) {
                    console.log("[!] REQUEST FAILED: " + e);
                    throw e;
                }
            };

            RealCall.enqueue.implementation = function(callback) {
                var request = this.request();
                var url = request.url().toString();
                console.log("[ASYNC] " + request.method() + " " + url.substring(0, 80));
                return this.enqueue(callback);
            };

            console.log("[+] OkHttp request/response logging enabled");
        } catch(e) {
            console.log("[-] RealCall hook: " + e);
        }

        // 6. Log connectivity checks
        try {
            var ConnectivityManager = Java.use("android.net.ConnectivityManager");
            ConnectivityManager.getActiveNetworkInfo.implementation = function() {
                var result = this.getActiveNetworkInfo();
                console.log("[NET] getActiveNetworkInfo: " + result);
                return result;
            };
        } catch(e) {}

        // 7. Hook network error handling
        try {
            var IOException = Java.use("java.io.IOException");
            IOException.$init.overload('java.lang.String').implementation = function(msg) {
                if (msg && msg.indexOf("ssl") !== -1 || msg && msg.indexOf("SSL") !== -1 ||
                    msg && msg.indexOf("certificate") !== -1 || msg && msg.indexOf("Certificate") !== -1) {
                    console.log("[!] SSL IOException: " + msg);
                }
                return this.$init(msg);
            };
        } catch(e) {}

        // 8. Monitor WebSocket connections (Avito messenger uses them)
        try {
            var WebSocket = Java.use("okhttp3.WebSocket");
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.connect.implementation = function(client) {
                var url = this.request().url().toString();
                console.log("[WS] WebSocket connecting: " + url);
                return this.connect(client);
            };
        } catch(e) {}

        console.log("\n[*] DEBUG MODE ready! Try to use the app...\n");
    });
}, 2000);
