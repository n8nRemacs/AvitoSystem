// Registration & Auth Flow Capture - targets VK ID and Avito auth classes
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Registration/Auth Flow Capture\n");

        // ============ WebSocket (already working) ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 || text.indexOf("session") !== -1) {
                    console.log("\n>>> WS AUTH: " + text);
                }
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 || text.indexOf("session") !== -1 || text.indexOf("error") !== -1) {
                    console.log("\n<<< WS AUTH: " + text);
                }
                return this.onReadMessage(text);
            };
            console.log("[+] WebSocket hooked");
        } catch(e) {
            console.log("[-] WebSocket: " + e);
        }

        // ============ VK ID Captcha Classes ============
        try {
            var VKCaptcha = Java.use("com.vk.id.captcha.api.VKCaptcha");
            VKCaptcha["$init"].implementation = function() {
                console.log("\n[CAPTCHA] VKCaptcha initialized!");
                return this["$init"]();
            };
        } catch(e) {}

        try {
            var CaptchaInterceptor = Java.use("com.vk.id.captcha.okhttp.api.CaptchaHandlingInterceptor");
            CaptchaInterceptor.intercept.implementation = function(chain) {
                var request = chain.request();
                console.log("\n[CAPTCHA INTERCEPT] " + request.url().toString());
                return this.intercept(chain);
            };
        } catch(e) {}

        // ============ Avito Captcha Interceptor ============
        try {
            var AvitoCaptcha = Java.use("com.avito.android.captcha.interceptor.a");
            AvitoCaptcha.intercept.implementation = function(chain) {
                var request = chain.request();
                console.log("\n[AVITO CAPTCHA] URL: " + request.url().toString());
                var response = this.intercept(chain);
                console.log("[AVITO CAPTCHA] Response: " + response.code());
                return response;
            };
        } catch(e) {}

        // ============ HttpURLConnection (fallback for non-OkHttp) ============
        try {
            var URL = Java.use("java.net.URL");
            var HttpURLConnection = Java.use("java.net.HttpURLConnection");

            URL.openConnection.overload().implementation = function() {
                var url = this.toString();
                if (url.indexOf("avito") !== -1 || url.indexOf("vk.") !== -1 ||
                    url.indexOf("auth") !== -1 || url.indexOf("captcha") !== -1) {
                    console.log("\n[HTTP] Opening: " + url);
                }
                return this.openConnection();
            };
            console.log("[+] URL.openConnection hooked");
        } catch(e) {}

        // ============ OkHttp Builder - to find actual client ============
        try {
            var OkHttpClientBuilder = Java.use("okhttp3.OkHttpClient$Builder");
            OkHttpClientBuilder.build.implementation = function() {
                console.log("[+] OkHttpClient built");
                var client = this.build();
                return client;
            };
        } catch(e) {}

        // ============ Retrofit (if used) ============
        try {
            var Retrofit = Java.use("retrofit2.Retrofit");
            Retrofit.create.implementation = function(service) {
                console.log("[RETROFIT] Creating service: " + service.getName());
                return this.create(service);
            };
        } catch(e) {}

        // ============ Search for auth-related Avito classes ============
        console.log("\n[*] Searching for auth classes...\n");

        Java.enumerateLoadedClasses({
            onMatch: function(className) {
                var lc = className.toLowerCase();
                if ((lc.indexOf("avito") !== -1 || lc.indexOf("vk.id") !== -1) &&
                    (lc.indexOf("auth") !== -1 || lc.indexOf("login") !== -1 ||
                     lc.indexOf("phone") !== -1 || lc.indexOf("sms") !== -1 ||
                     lc.indexOf("otp") !== -1 || lc.indexOf("verify") !== -1 ||
                     lc.indexOf("register") !== -1 || lc.indexOf("signup") !== -1)) {
                    console.log("[AUTH CLASS] " + className);
                }
            },
            onComplete: function() {
                console.log("\n[*] Class search complete\n");
            }
        });

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

        console.log("\n[*] Ready! Start registration with new phone number...\n");
    });
}, 1000);
