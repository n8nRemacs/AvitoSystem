// Avito Auth & Session Capture
// Captures authentication flow and session tokens

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito Auth Capture v1.0\n");

        // ============ SSL BYPASS (minimal) ============
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");
            try { CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {}; } catch(e) {}
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
                name: 'dev.avito.TrustAllAuth',
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

        // ============ SESSION CAPTURE ============

        // Hook SharedPreferences for session data
        try {
            var SharedPreferencesImpl = Java.use("android.app.SharedPreferencesImpl");

            SharedPreferencesImpl.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
                var result = this.getString(key, defValue);
                var keyLower = key.toLowerCase();
                if (keyLower.indexOf("session") !== -1 ||
                    keyLower.indexOf("token") !== -1 ||
                    keyLower.indexOf("auth") !== -1 ||
                    keyLower.indexOf("user") !== -1 ||
                    keyLower.indexOf("cookie") !== -1 ||
                    keyLower.indexOf("sessid") !== -1 ||
                    keyLower.indexOf("credential") !== -1 ||
                    keyLower.indexOf("password") !== -1 ||
                    keyLower.indexOf("phone") !== -1 ||
                    keyLower.indexOf("login") !== -1) {
                    console.log("\n[PREF GET] " + key);
                    if (result && result.length < 500) {
                        console.log("  Value: " + result);
                    } else if (result) {
                        console.log("  Value: " + result.substring(0, 200) + "...");
                    }
                }
                return result;
            };

            SharedPreferencesImpl.putString.overload('java.lang.String', 'java.lang.String').implementation = function(key, value) {
                var keyLower = key.toLowerCase();
                if (keyLower.indexOf("session") !== -1 ||
                    keyLower.indexOf("token") !== -1 ||
                    keyLower.indexOf("auth") !== -1 ||
                    keyLower.indexOf("cookie") !== -1 ||
                    keyLower.indexOf("sessid") !== -1 ||
                    keyLower.indexOf("credential") !== -1) {
                    console.log("\n[PREF SET] " + key);
                    if (value && value.length < 500) {
                        console.log("  Value: " + value);
                    } else if (value) {
                        console.log("  Value: " + value.substring(0, 200) + "...");
                    }
                }
                return this.putString(key, value);
            };

            console.log("[+] SharedPreferences hooks installed");
        } catch(e) {
            console.log("[-] SharedPreferences: " + e);
        }

        // Hook Editor.putString for writes
        try {
            var Editor = Java.use("android.app.SharedPreferencesImpl$EditorImpl");
            Editor.putString.implementation = function(key, value) {
                var keyLower = key.toLowerCase();
                if (keyLower.indexOf("session") !== -1 ||
                    keyLower.indexOf("token") !== -1 ||
                    keyLower.indexOf("auth") !== -1 ||
                    keyLower.indexOf("cookie") !== -1 ||
                    keyLower.indexOf("sessid") !== -1) {
                    console.log("\n[PREF WRITE] " + key);
                    if (value && value.length < 500) {
                        console.log("  Value: " + value);
                    }
                }
                return this.putString(key, value);
            };
        } catch(e) {}

        // ============ COOKIE CAPTURE ============

        try {
            var CookieJar = Java.use("okhttp3.CookieJar");
            var Cookie = Java.use("okhttp3.Cookie");

            // Try to hook JavaNetCookieJar
            try {
                var JavaNetCookieJar = Java.use("okhttp3.JavaNetCookieJar");
                JavaNetCookieJar.saveFromResponse.implementation = function(url, cookies) {
                    console.log("\n[COOKIE SAVE] " + url.toString());
                    var iter = cookies.iterator();
                    while (iter.hasNext()) {
                        var cookie = iter.next();
                        console.log("  " + cookie.name() + "=" + cookie.value());
                    }
                    return this.saveFromResponse(url, cookies);
                };
            } catch(e) {}
        } catch(e) {}

        // Hook Set-Cookie header parsing
        try {
            var Headers = Java.use("okhttp3.Headers");
            Headers.get.overload('java.lang.String').implementation = function(name) {
                var result = this.get(name);
                if (name.toLowerCase() === "set-cookie" && result) {
                    console.log("\n[SET-COOKIE] " + result);
                }
                return result;
            };
        } catch(e) {}

        // ============ AUTH API CAPTURE ============

        // Hook auth-related URL requests
        try {
            var RealInterceptorChain = null;
            try {
                RealInterceptorChain = Java.use("okhttp3.internal.http.RealInterceptorChain");
            } catch(e) {
                RealInterceptorChain = Java.use("okhttp3.RealInterceptorChain");
            }

            if (RealInterceptorChain) {
                RealInterceptorChain.proceed.overload('okhttp3.Request').implementation = function(request) {
                    var url = request.url().toString();
                    var urlLower = url.toLowerCase();

                    // Capture auth-related requests
                    if (urlLower.indexOf("auth") !== -1 ||
                        urlLower.indexOf("login") !== -1 ||
                        urlLower.indexOf("token") !== -1 ||
                        urlLower.indexOf("session") !== -1 ||
                        urlLower.indexOf("phone") !== -1 ||
                        urlLower.indexOf("code") !== -1 ||
                        urlLower.indexOf("verify") !== -1 ||
                        urlLower.indexOf("credential") !== -1 ||
                        urlLower.indexOf("oauth") !== -1 ||
                        urlLower.indexOf("sms") !== -1) {

                        console.log("\n========== AUTH REQUEST ==========");
                        console.log("[URL] " + url);
                        console.log("[Method] " + request.method());

                        // Log ALL headers
                        var headers = request.headers();
                        var size = headers.size();
                        console.log("[Headers]");
                        for (var i = 0; i < size; i++) {
                            console.log("  " + headers.name(i) + ": " + headers.value(i));
                        }

                        // Log body
                        var body = request.body();
                        if (body !== null) {
                            try {
                                var Buffer = Java.use("okio.Buffer");
                                var buffer = Buffer.$new();
                                body.writeTo(buffer);
                                var bodyStr = buffer.readUtf8();
                                console.log("[Body] " + bodyStr);
                            } catch(e) {
                                console.log("[Body] (error reading)");
                            }
                        }
                    }

                    var response = this.proceed(request);

                    // Capture auth response
                    if (urlLower.indexOf("auth") !== -1 ||
                        urlLower.indexOf("login") !== -1 ||
                        urlLower.indexOf("token") !== -1 ||
                        urlLower.indexOf("session") !== -1 ||
                        urlLower.indexOf("phone") !== -1 ||
                        urlLower.indexOf("code") !== -1 ||
                        urlLower.indexOf("verify") !== -1) {

                        console.log("\n---------- AUTH RESPONSE ----------");
                        console.log("[Code] " + response.code());

                        // Log response headers
                        var respHeaders = response.headers();
                        var respSize = respHeaders.size();
                        for (var j = 0; j < respSize; j++) {
                            var hName = respHeaders.name(j);
                            if (hName.toLowerCase().indexOf("cookie") !== -1 ||
                                hName.toLowerCase().indexOf("auth") !== -1 ||
                                hName.toLowerCase().indexOf("token") !== -1) {
                                console.log("  " + hName + ": " + respHeaders.value(j));
                            }
                        }

                        // Try to read response body
                        try {
                            var bodyStr = response.peekBody(Java.use("java.lang.Long").parseLong("10240")).string();
                            if (bodyStr.length < 2000) {
                                console.log("[Response] " + bodyStr);
                            } else {
                                console.log("[Response] " + bodyStr.substring(0, 500) + "...");
                            }
                        } catch(e) {}

                        console.log("===================================\n");
                    }

                    return response;
                };
                console.log("[+] HTTP interceptor installed");
            }
        } catch(e) {
            console.log("[-] HTTP interceptor: " + e);
        }

        // ============ SESSION PROVIDER HOOKS ============

        // Hook SessionCookieProvider
        try {
            var SessionCookieProvider = Java.use("com.avito.android.remote.interceptor.C0");
            SessionCookieProvider.b.implementation = function() {
                var result = this.b();
                console.log("\n[SESSION COOKIE] " + result);
                return result;
            };
        } catch(e) {}

        // Hook SessionHeaderProvider
        try {
            var SessionHeaderProvider = Java.use("com.avito.android.remote.interceptor.G0");
            SessionHeaderProvider.b.implementation = function() {
                var result = this.b();
                console.log("\n[SESSION HEADER] " + result);
                return result;
            };
        } catch(e) {}

        // ============ MESSENGER SESSION ============

        // Hook messenger session provider
        try {
            var MessengerSession = Java.use("ru.avito.messenger.C0");
            if (MessengerSession.d) {
                MessengerSession.d.implementation = function() {
                    var result = this.d();
                    console.log("\n[MESSENGER SESSION] Retrieved");
                    return result;
                };
            }
        } catch(e) {}

        // ============ WebSocket CAPTURE ============

        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 ||
                    text.indexOf("session") !== -1 ||
                    text.indexOf("login") !== -1 ||
                    text.indexOf("token") !== -1) {
                    console.log("\n[WS SEND AUTH] " + text.substring(0, Math.min(text.length, 500)));
                }
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 ||
                    text.indexOf("session") !== -1 ||
                    text.indexOf("error") !== -1 ||
                    text.indexOf("token") !== -1) {
                    console.log("\n[WS RECV] " + text.substring(0, Math.min(text.length, 500)));
                }
                return this.onReadMessage(text);
            };

            console.log("[+] WebSocket hooks installed");
        } catch(e) {}

        console.log("\n[*] Auth Capture ready!");
        console.log("[*] Now login to Avito to capture authentication flow\n");
    });
}, 2000);
