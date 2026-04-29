// Universal SSL Pinning Bypass for Android
// Disables certificate validation in OkHttp, SSLContext, TrustManager, WebView, etc.
// Used with Frida spawn mode to inject before app init.

Java.perform(function() {
    send("[*] SSL Pinning Bypass starting...");

    // === 1. OkHttp3 CertificatePinner ===
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function(hostname, peerCerts) {
            send("[SSL] OkHttp3 CertificatePinner.check bypassed for: " + hostname);
        };
    } catch(e) {}

    // OkHttp3 CertificatePinner$check$okhttp (Kotlin variant)
    try {
        var CertificatePinner2 = Java.use("okhttp3.CertificatePinner");
        CertificatePinner2["check$okhttp"].implementation = function(hostname, cleanFn) {
            send("[SSL] OkHttp3 CertificatePinner.check$okhttp bypassed for: " + hostname);
        };
    } catch(e) {}

    // === 2. TrustManagerImpl (Android system) ===
    try {
        var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            send("[SSL] TrustManagerImpl.verifyChain bypassed for: " + host);
            return untrustedChain;
        };
    } catch(e) {}

    // === 3. Custom X509TrustManager — accept all ===
    try {
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        var TrustManager = Java.registerClass({
            name: "com.bypass.TrustAllManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function(chain, authType) {},
                checkServerTrusted: function(chain, authType) {},
                getAcceptedIssuers: function() { return []; }
            }
        });

        // Hook SSLContext.init to inject our TrustManager
        SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom").implementation = function(km, tm, sr) {
            send("[SSL] SSLContext.init intercepted — injecting TrustAll");
            var trustAll = Java.array("javax.net.ssl.TrustManager", [TrustManager.$new()]);
            this.init(km, trustAll, sr);
        };
    } catch(e) { send("[!] SSLContext hook failed: " + e); }

    // === 4. OkHttpClient.Builder — remove certificate pinner ===
    try {
        var OkHttpClientBuilder = Java.use("okhttp3.OkHttpClient$Builder");
        OkHttpClientBuilder.certificatePinner.implementation = function(certPinner) {
            send("[SSL] OkHttpClient.Builder.certificatePinner stripped");
            return this;
        };
    } catch(e) {}

    // === 5. HostnameVerifier — accept all hostnames ===
    try {
        var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
        var AllHostsVerifier = Java.registerClass({
            name: "com.bypass.AllHostsVerifier",
            implements: [HostnameVerifier],
            methods: {
                verify: function(hostname, session) {
                    return true;
                }
            }
        });

        var HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
        HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(verifier) {
            send("[SSL] HttpsURLConnection.setDefaultHostnameVerifier → AllHosts");
            this.setDefaultHostnameVerifier(AllHostsVerifier.$new());
        };
        HttpsURLConnection.setHostnameVerifier.implementation = function(verifier) {
            send("[SSL] HttpsURLConnection.setHostnameVerifier → AllHosts");
            this.setHostnameVerifier(AllHostsVerifier.$new());
        };
    } catch(e) {}

    // === 6. NetworkSecurityConfig (Android 7+) ===
    try {
        var NetworkSecurityConfig = Java.use("android.security.net.config.NetworkSecurityConfig");
        NetworkSecurityConfig.isCleartextTrafficPermitted.overload().implementation = function() {
            send("[SSL] NetworkSecurityConfig.isCleartextTrafficPermitted → true");
            return true;
        };
    } catch(e) {}

    // === 7. Conscrypt / OpenSSLSocketImpl ===
    try {
        var OpenSSLSocketImpl = Java.use("com.android.org.conscrypt.OpenSSLSocketImpl");
        OpenSSLSocketImpl.verifyCertificateChain.implementation = function(certRefs, authMethod) {
            send("[SSL] OpenSSLSocketImpl.verifyCertificateChain bypassed");
        };
    } catch(e) {}

    try {
        var ConscryptPlatform = Java.use("com.android.org.conscrypt.Platform");
        ConscryptPlatform.checkServerTrusted.overload("javax.net.ssl.X509TrustManager", "[Ljava.security.cert.X509Certificate;", "java.lang.String", "com.android.org.conscrypt.AbstractConscryptSocket").implementation = function(tm, chain, authType, socket) {
            send("[SSL] Conscrypt Platform.checkServerTrusted bypassed");
        };
    } catch(e) {}

    // === 8. WebViewClient SSL errors — proceed ===
    try {
        var WebViewClient = Java.use("android.webkit.WebViewClient");
        WebViewClient.onReceivedSslError.implementation = function(view, handler, error) {
            send("[SSL] WebViewClient.onReceivedSslError → proceed");
            handler.proceed();
        };
    } catch(e) {}

    // === 9. TrustManagerFactory — return permissive TrustManagers ===
    try {
        var TMF = Java.use("javax.net.ssl.TrustManagerFactory");
        TMF.getTrustManagers.implementation = function() {
            send("[SSL] TrustManagerFactory.getTrustManagers → TrustAll");
            var X509TM = Java.use("javax.net.ssl.X509TrustManager");
            var AllTrust = Java.registerClass({
                name: "com.bypass.TMFAllTrust",
                implements: [X509TM],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });
            return Java.array("javax.net.ssl.TrustManager", [AllTrust.$new()]);
        };
    } catch(e) {}

    // === 10. Apache HTTP client (legacy) ===
    try {
        var AbstractVerifier = Java.use("org.apache.http.conn.ssl.AbstractVerifier");
        AbstractVerifier.verify.overload("java.lang.String", "[Ljava.lang.String;", "[Ljava.lang.String;", "boolean").implementation = function(host, cns, subjectAlts, strictWithSubDomains) {
            send("[SSL] Apache AbstractVerifier.verify bypassed for: " + host);
        };
    } catch(e) {}

    send("[*] SSL Pinning Bypass installed (10 hooks)");
});
