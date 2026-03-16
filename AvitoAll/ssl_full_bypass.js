/*
 * Full SSL Unpinning Script
 * Based on multiple sources including frida-android-unpinning
 */

setTimeout(function() {
    Java.perform(function() {
        console.log("[*] Full SSL Unpinning loaded");

        // Create a TrustManager that trusts all certificates
        var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
        var TrustAllCerts = Java.registerClass({
            name: 'com.bypass.TrustAllCerts',
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function(chain, authType) {},
                checkServerTrusted: function(chain, authType) {},
                getAcceptedIssuers: function() { return []; }
            }
        });

        // 1. SSLContext.init - replace all TrustManagers
        try {
            var SSLContext = Java.use('javax.net.ssl.SSLContext');
            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                console.log('[+] SSLContext.init intercepted');
                var trustAll = Java.array('javax.net.ssl.X509TrustManager', [TrustAllCerts.$new()]);
                this.init(km, trustAll, sr);
            };
            console.log("[+] SSLContext.init hooked");
        } catch(e) {
            console.log("[-] SSLContext.init: " + e);
        }

        // 2. TrustManagerFactory.getTrustManagers
        try {
            var TrustManagerFactory = Java.use('javax.net.ssl.TrustManagerFactory');
            TrustManagerFactory.getTrustManagers.implementation = function() {
                console.log('[+] TrustManagerFactory.getTrustManagers intercepted');
                return Java.array('javax.net.ssl.TrustManager', [TrustAllCerts.$new()]);
            };
            console.log("[+] TrustManagerFactory hooked");
        } catch(e) {
            console.log("[-] TrustManagerFactory: " + e);
        }

        // 3. OkHttp CertificatePinner - all overloads
        try {
            var CertificatePinner = Java.use('okhttp3.CertificatePinner');

            if (CertificatePinner.check) {
                var overloads = CertificatePinner.check.overloads;
                for (var i = 0; i < overloads.length; i++) {
                    overloads[i].implementation = function() {
                        console.log('[+] OkHttp CertificatePinner.check bypassed');
                        return;
                    };
                }
            }

            // Also hook check$okhttp
            try {
                CertificatePinner['check$okhttp'].implementation = function() {
                    console.log('[+] OkHttp check$okhttp bypassed');
                    return;
                };
            } catch(e) {}

            console.log("[+] OkHttp CertificatePinner hooked");
        } catch(e) {
            console.log("[-] OkHttp CertificatePinner: " + e);
        }

        // 4. TrustManagerImpl.verifyChain (Android 7+)
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
                console.log('[+] TrustManagerImpl.verifyChain bypassed: ' + host);
                return untrustedChain;
            };
            console.log("[+] TrustManagerImpl hooked");
        } catch(e) {
            console.log("[-] TrustManagerImpl: " + e);
        }

        // 5. TrustManagerImpl.checkTrustedRecursive (Android)
        try {
            var TrustManagerImpl2 = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl2.checkTrustedRecursive.implementation = function(certs, host, clientAuth, untrustedChain, trustAnchorChain, used) {
                console.log('[+] TrustManagerImpl.checkTrustedRecursive bypassed');
                return Java.use('java.util.ArrayList').$new();
            };
        } catch(e) {}

        // 6. Network Security Config (Android 7+)
        try {
            var NetworkSecurityConfig = Java.use('android.security.net.config.NetworkSecurityTrustManager');
            NetworkSecurityConfig.checkServerTrusted.overload('[Ljava.security.cert.X509Certificate;', 'java.lang.String').implementation = function(certs, authType) {
                console.log('[+] NetworkSecurityTrustManager.checkServerTrusted bypassed');
            };
            NetworkSecurityConfig.checkServerTrusted.overload('[Ljava.security.cert.X509Certificate;', 'java.lang.String', 'java.lang.String').implementation = function(certs, authType, host) {
                console.log('[+] NetworkSecurityTrustManager.checkServerTrusted bypassed for: ' + host);
                return Java.use('java.util.ArrayList').$new();
            };
            console.log("[+] NetworkSecurityTrustManager hooked");
        } catch(e) {
            console.log("[-] NetworkSecurityTrustManager: " + e);
        }

        // 7. WebViewClient onReceivedSslError
        try {
            var WebViewClient = Java.use('android.webkit.WebViewClient');
            WebViewClient.onReceivedSslError.implementation = function(view, handler, error) {
                console.log('[+] WebViewClient.onReceivedSslError - proceeding');
                handler.proceed();
            };
            console.log("[+] WebViewClient hooked");
        } catch(e) {}

        // 8. Search for and hook any Interceptor classes with "certificate", "pin", or "ssl" in name
        console.log("[*] Searching for custom pinning classes...");

        Java.enumerateLoadedClasses({
            onMatch: function(className) {
                var lower = className.toLowerCase();
                if ((lower.includes('certificat') || lower.includes('pinning') || lower.includes('ssl')) &&
                    lower.includes('avito') &&
                    !lower.includes('$')) {
                    console.log('[*] Found potential class: ' + className);
                    try {
                        var clazz = Java.use(className);
                        var methods = clazz.class.getDeclaredMethods();
                        for (var i = 0; i < methods.length; i++) {
                            var methodName = methods[i].getName();
                            if (methodName === 'intercept' || methodName === 'check' || methodName === 'verify') {
                                console.log('[*] Hooking: ' + className + '.' + methodName);
                            }
                        }
                    } catch(e) {}
                }
            },
            onComplete: function() {
                console.log("[*] Class search complete");
            }
        });

        // 9. Hook all OkHttp Interceptor.intercept methods to find pinning interceptor
        try {
            var Interceptor = Java.use('okhttp3.Interceptor');
            Java.choose('okhttp3.Interceptor', {
                onMatch: function(instance) {
                    console.log('[*] Found Interceptor instance: ' + instance.getClass().getName());
                },
                onComplete: function() {}
            });
        } catch(e) {}

        // 10. HostnameVerifier - accept all
        try {
            var HostnameVerifier = Java.use('javax.net.ssl.HostnameVerifier');
            var AllowAll = Java.registerClass({
                name: 'com.bypass.AllowAllHostnames',
                implements: [HostnameVerifier],
                methods: {
                    verify: function(hostname, session) {
                        console.log('[+] HostnameVerifier.verify bypassed for: ' + hostname);
                        return true;
                    }
                }
            });

            var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
            HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(verifier) {
                console.log('[+] HttpsURLConnection.setDefaultHostnameVerifier intercepted');
                this.setDefaultHostnameVerifier(AllowAll.$new());
            };
            HttpsURLConnection.setHostnameVerifier.implementation = function(verifier) {
                console.log('[+] HttpsURLConnection.setHostnameVerifier intercepted');
                this.setHostnameVerifier(AllowAll.$new());
            };
            console.log("[+] HostnameVerifier hooked");
        } catch(e) {
            console.log("[-] HostnameVerifier: " + e);
        }

        console.log("\n[*] SSL Unpinning READY!");
        console.log("[*] Now open Avito and try to login\n");
    });
}, 500);
