/*
 * Simple SSL Unpinning - no class enumeration
 */

Java.perform(function() {
    console.log("[*] Simple SSL Unpinning");

    // TrustManager that trusts all
    var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
    var TrustAll = Java.registerClass({
        name: 'com.bypass.TrustAll',
        implements: [X509TrustManager],
        methods: {
            checkClientTrusted: function(chain, authType) {},
            checkServerTrusted: function(chain, authType) {},
            getAcceptedIssuers: function() { return []; }
        }
    });

    // 1. SSLContext.init
    try {
        var SSLContext = Java.use('javax.net.ssl.SSLContext');
        SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
            console.log('[+] SSLContext.init bypassed');
            this.init(km, Java.array('javax.net.ssl.X509TrustManager', [TrustAll.$new()]), sr);
        };
    } catch(e) { console.log("[-] SSLContext: " + e); }

    // 2. TrustManagerImpl.verifyChain
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            console.log('[+] TrustManagerImpl bypassed: ' + host);
            return untrustedChain;
        };
    } catch(e) { console.log("[-] TrustManagerImpl: " + e); }

    // 3. OkHttp CertificatePinner
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {
            console.log('[+] OkHttp CertificatePinner bypassed: ' + a);
        };
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {
            console.log('[+] OkHttp CertificatePinner bypassed: ' + a);
        };
    } catch(e) { console.log("[-] OkHttp: " + e); }

    // 4. Avito CertificatePinningInterceptorImpl (C34315x)
    try {
        var AvitoInterceptor = Java.use('com.avito.android.remote.interceptor.C34315x');
        AvitoInterceptor.intercept.implementation = function(chain) {
            console.log('[+] Avito CertificatePinningInterceptorImpl bypassed');
            return chain.proceed(chain.request());
        };
        console.log("[+] Avito interceptor C34315x hooked");
    } catch(e) {
        console.log("[-] C34315x: " + e);
        // Try alternative class name
        try {
            var AvitoInterceptor2 = Java.use('com.avito.android.remote.interceptor.x');
            AvitoInterceptor2.intercept.implementation = function(chain) {
                console.log('[+] Avito interceptor.x bypassed');
                return chain.proceed(chain.request());
            };
            console.log("[+] Avito interceptor.x hooked");
        } catch(e2) { console.log("[-] interceptor.x: " + e2); }
    }

    // 5. Avito certificate_pinning.b class
    try {
        var AvitoPinB = Java.use('com.avito.android.certificate_pinning.b');
        // Hook any methods that might check certificates
        console.log("[+] Found certificate_pinning.b");
    } catch(e) { console.log("[-] certificate_pinning.b: " + e); }

    // 6. Hook InterfaceC34313w implementations
    try {
        var PinInterface = Java.use('com.avito.android.remote.interceptor.InterfaceC34313w');
        console.log("[+] Found InterfaceC34313w");
    } catch(e) {}

    // 7. Block CertificatePinningError creation
    try {
        var ApiError = Java.use('com.avito.android.remote.error.ApiError$CertificatePinningError');
        ApiError.$init.overload('java.lang.String', 'boolean').implementation = function(msg, flag) {
            console.log('[!] CertificatePinningError blocked: ' + msg);
            return this.$init("bypassed", false);
        };
        console.log("[+] ApiError.CertificatePinningError hooked");
    } catch(e) { console.log("[-] CertificatePinningError: " + e); }

    console.log("[*] SSL Unpinning READY!");
});
