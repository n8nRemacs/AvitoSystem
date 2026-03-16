// Aggressive SSL Pinning Bypass for Avito
// Kills ALL certificate validation

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito SSL Killer v2.0\n");

        // 1. Kill OkHttp CertificatePinner - ALL overloads
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");

            // Method 1
            try {
                CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {
                    console.log("[+] CertificatePinner.check(String,List) killed: " + a);
                };
            } catch(e) {}

            // Method 2
            try {
                CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {
                    console.log("[+] CertificatePinner.check(String,Cert[]) killed: " + a);
                };
            } catch(e) {}

            // Method 3 - check$okhttp
            try {
                CertificatePinner['check$okhttp'].implementation = function(a, b) {
                    console.log("[+] CertificatePinner.check$okhttp killed: " + a);
                };
            } catch(e) {}

            console.log("[+] OkHttp CertificatePinner neutralized");
        } catch(e) {
            console.log("[-] CertificatePinner: " + e);
        }

        // 2. Kill CertificatePinner.Builder.add
        try {
            var CertificatePinnerBuilder = Java.use("okhttp3.CertificatePinner$Builder");
            CertificatePinnerBuilder.add.overload('java.lang.String', '[Ljava.lang.String;').implementation = function(host, pins) {
                console.log("[+] CertificatePinner.Builder.add blocked: " + host);
                return this;
            };
            console.log("[+] CertificatePinner.Builder neutralized");
        } catch(e) {
            console.log("[-] Builder: " + e);
        }

        // 3. Return empty CertificatePinner
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");
            var CertificatePinnerBuilder = Java.use("okhttp3.CertificatePinner$Builder");
            var emptyPinner = CertificatePinnerBuilder.$new().build();

            var OkHttpClientBuilder = Java.use("okhttp3.OkHttpClient$Builder");
            OkHttpClientBuilder.certificatePinner.implementation = function(pinner) {
                console.log("[+] OkHttpClient.Builder.certificatePinner replaced with empty");
                return this.certificatePinner(emptyPinner);
            };
            console.log("[+] OkHttpClient.Builder patched");
        } catch(e) {
            console.log("[-] OkHttpClient.Builder: " + e);
        }

        // 4. Kill TrustManagerImpl.checkServerTrusted
        try {
            var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");

            TrustManagerImpl.checkServerTrusted.overload('[Ljava.security.cert.X509Certificate;', 'java.lang.String').implementation = function(certs, authType) {
                console.log("[+] TrustManagerImpl.checkServerTrusted bypassed");
            };

            TrustManagerImpl.checkServerTrusted.overload('[Ljava.security.cert.X509Certificate;', 'java.lang.String', 'java.lang.String').implementation = function(certs, authType, host) {
                console.log("[+] TrustManagerImpl.checkServerTrusted(3) bypassed: " + host);
            };

            console.log("[+] TrustManagerImpl neutralized");
        } catch(e) {
            console.log("[-] TrustManagerImpl: " + e);
        }

        // 5. Kill verifyChain
        try {
            var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
            TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
                console.log("[+] verifyChain bypassed: " + host);
                return untrustedChain;
            };
            console.log("[+] verifyChain patched");
        } catch(e) {
            console.log("[-] verifyChain: " + e);
        }

        // 6. Kill Avito specific classes
        var avitoClasses = [
            "com.avito.android.certificate_pinning.domain.e",
            "com.avito.android.certificate_pinning.domain.CertificatePinningInterceptor",
            "com.avito.android.remote.interceptor.C34315x",
            "com.avito.android.remote.interceptor.x"
        ];

        avitoClasses.forEach(function(className) {
            try {
                var cls = Java.use(className);
                cls.intercept.implementation = function(chain) {
                    console.log("[+] " + className + " bypassed");
                    return chain.proceed(chain.request());
                };
                console.log("[+] Hooked: " + className);
            } catch(e) {}
        });

        // 7. Nuclear option - hook ALL Interceptor.intercept
        try {
            Java.enumerateLoadedClasses({
                onMatch: function(className) {
                    if (className.indexOf("avito") !== -1 &&
                        (className.indexOf("pinning") !== -1 || className.indexOf("Pinning") !== -1 ||
                         className.indexOf("certificate") !== -1 || className.indexOf("Certificate") !== -1)) {
                        try {
                            var cls = Java.use(className);
                            var methods = cls.class.getDeclaredMethods();
                            console.log("[*] Found: " + className);
                        } catch(e) {}
                    }
                },
                onComplete: function() {}
            });
        } catch(e) {}

        // 8. Patch SSLContext
        try {
            var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var SSLContext = Java.use('javax.net.ssl.SSLContext');

            var TrustManager = Java.registerClass({
                name: 'dev.avito.TrustAllX509',
                implements: [X509TrustManager],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });

            var TrustManagers = [TrustManager.$new()];
            var TLSContext = SSLContext.getInstance("TLS");
            TLSContext.init(null, TrustManagers, null);

            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                console.log("[+] SSLContext.init hijacked");
                this.init(km, TrustManagers, sr);
            };
            console.log("[+] SSLContext patched");
        } catch(e) {
            console.log("[-] SSLContext: " + e);
        }

        // 9. Patch SSLSocketFactory
        try {
            var SSLSocketFactory = Java.use('javax.net.ssl.SSLSocketFactory');
            SSLSocketFactory.getDefault.implementation = function() {
                console.log("[+] SSLSocketFactory.getDefault intercepted");
                var TLSContext = Java.use('javax.net.ssl.SSLContext').getInstance("TLS");

                var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
                var TrustAll = Java.registerClass({
                    name: 'dev.avito.TrustAll2',
                    implements: [X509TrustManager],
                    methods: {
                        checkClientTrusted: function(c, a) {},
                        checkServerTrusted: function(c, a) {},
                        getAcceptedIssuers: function() { return []; }
                    }
                });
                TLSContext.init(null, [TrustAll.$new()], null);
                return TLSContext.getSocketFactory();
            };
        } catch(e) {}

        console.log("\n[*] SSL Killer ready! Restart Avito and try again.\n");
    });
}, 2000);
