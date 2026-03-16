// Avito SSL Killer v3.0 - hooks ALL discovered pinning classes
// Based on enumerated classes from v2.0

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Avito SSL Killer v3.0\n");

        // 1. Kill OkHttp CertificatePinner - ALL overloads
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");

            try {
                CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {
                    console.log("[+] CertificatePinner.check(String,List) killed: " + a);
                };
            } catch(e) {}

            try {
                CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {
                    console.log("[+] CertificatePinner.check(String,Cert[]) killed: " + a);
                };
            } catch(e) {}

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

        // 6. Kill ALL Avito certificate pinning classes - hook intercept method
        var avitoInterceptors = [
            "com.avito.android.certificate_pinning.domain.e",
            "com.avito.android.certificate_pinning.domain.CertificatePinningInterceptor",
            "com.avito.android.remote.interceptor.C34315x",
            "com.avito.android.remote.interceptor.x"
        ];

        avitoInterceptors.forEach(function(className) {
            try {
                var cls = Java.use(className);
                cls.intercept.implementation = function(chain) {
                    console.log("[+] " + className + ".intercept bypassed");
                    return chain.proceed(chain.request());
                };
                console.log("[+] Hooked: " + className);
            } catch(e) {}
        });

        // 7. Hook ALL certificate_pinning domain classes
        var pinningDomainClasses = [
            "com.avito.android.certificate_pinning.domain.a",
            "com.avito.android.certificate_pinning.domain.b",
            "com.avito.android.certificate_pinning.domain.c",
            "com.avito.android.certificate_pinning.domain.d",
            "com.avito.android.certificate_pinning.domain.e",
            "com.avito.android.certificate_pinning.domain.f"
        ];

        pinningDomainClasses.forEach(function(className) {
            try {
                var cls = Java.use(className);
                var methods = cls.class.getDeclaredMethods();
                methods.forEach(function(method) {
                    var methodName = method.getName();
                    // Hook methods that might check certificates
                    if (methodName.indexOf("check") !== -1 ||
                        methodName.indexOf("verify") !== -1 ||
                        methodName.indexOf("validate") !== -1 ||
                        methodName === "intercept") {
                        try {
                            cls[methodName].implementation = function() {
                                console.log("[+] " + className + "." + methodName + " bypassed");
                                // Return null/void for check methods
                            };
                        } catch(e) {}
                    }
                });
            } catch(e) {}
        });

        // 8. Hook certificate_pinning package classes
        var pinningClasses = [
            "com.avito.android.certificate_pinning.b",
            "com.avito.android.certificate_pinning.h",
            "com.avito.android.certificate_pinning.i",
            "com.avito.android.certificate_pinning.j",
            "com.avito.android.certificate_pinning.k",
            "com.avito.android.certificate_pinning.l",
            "com.avito.android.certificate_pinning.m",
            "com.avito.android.certificate_pinning.n",
            "com.avito.android.certificate_pinning.r",
            "com.avito.android.certificate_pinning.s"
        ];

        pinningClasses.forEach(function(className) {
            try {
                var cls = Java.use(className);
                // Try to hook intercept method if exists
                try {
                    cls.intercept.implementation = function(chain) {
                        console.log("[+] " + className + ".intercept bypassed");
                        return chain.proceed(chain.request());
                    };
                } catch(e) {}
            } catch(e) {}
        });

        // 9. Kill CertificatePinningException - make it never throw
        try {
            var CertPinException = Java.use("com.avito.android.util.CertificatePinningException");
            CertPinException.$init.overload('java.lang.String').implementation = function(msg) {
                console.log("[+] CertificatePinningException suppressed: " + msg);
                // Don't call original constructor - return empty exception
            };
            console.log("[+] CertificatePinningException hooked");
        } catch(e) {}

        // 10. Kill ApiError$CertificatePinningError
        try {
            var CertPinError = Java.use("com.avito.android.remote.error.ApiError$CertificatePinningError");
            CertPinError.$init.implementation = function() {
                console.log("[+] CertificatePinningError suppressed");
            };
        } catch(e) {}

        // 11. Kill UnsafeNetworkActivity check
        try {
            var UnsafeNetwork = Java.use("com.avito.android.certificate_pinning.UnsafeNetworkActivity");
            var methods = UnsafeNetwork.class.getDeclaredMethods();
            methods.forEach(function(method) {
                try {
                    var methodName = method.getName();
                    UnsafeNetwork[methodName].implementation = function() {
                        console.log("[+] UnsafeNetworkActivity." + methodName + " bypassed");
                        return null;
                    };
                } catch(e) {}
            });
        } catch(e) {}

        // 12. Patch SSLContext
        try {
            var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var SSLContext = Java.use('javax.net.ssl.SSLContext');

            var TrustManager = Java.registerClass({
                name: 'dev.avito.TrustAllX509v3',
                implements: [X509TrustManager],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });

            var TrustManagers = [TrustManager.$new()];

            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                console.log("[+] SSLContext.init hijacked");
                this.init(km, TrustManagers, sr);
            };
            console.log("[+] SSLContext patched");
        } catch(e) {
            console.log("[-] SSLContext: " + e);
        }

        // 13. Patch HostnameVerifier
        try {
            var HostnameVerifier = Java.use('javax.net.ssl.HostnameVerifier');
            var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');

            var TrustAllHostname = Java.registerClass({
                name: 'dev.avito.TrustAllHostname',
                implements: [HostnameVerifier],
                methods: {
                    verify: function(hostname, session) {
                        console.log("[+] HostnameVerifier.verify bypassed: " + hostname);
                        return true;
                    }
                }
            });

            HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(verifier) {
                console.log("[+] setDefaultHostnameVerifier hijacked");
                this.setDefaultHostnameVerifier(TrustAllHostname.$new());
            };
        } catch(e) {}

        // 14. Hook NetworkState to always return safe
        try {
            var NetworkState = Java.use("com.avito.android.certificate_pinning.NetworkState");
            try {
                NetworkState.isUnsafe.implementation = function() {
                    console.log("[+] NetworkState.isUnsafe -> false");
                    return false;
                };
            } catch(e) {}
            try {
                NetworkState.isSafe.implementation = function() {
                    console.log("[+] NetworkState.isSafe -> true");
                    return true;
                };
            } catch(e) {}
        } catch(e) {}

        console.log("\n[*] SSL Killer v3.0 ready! All hooks installed.\n");
    });
}, 2000);
