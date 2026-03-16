/**
 * SSL Unpinning Script for Android
 *
 * This script bypasses SSL certificate pinning in Android apps
 * allowing inspection of HTTPS traffic through proxy tools
 * like Charles Proxy, mitmproxy, or Burp Suite.
 *
 * Usage:
 *   frida -U -f com.avito.android -l ssl_unpin.js --no-pause
 */

Java.perform(function() {
    console.log("[*] SSL Unpinning script loaded");

    // Hook SSLContext
    var SSLContext = Java.use('javax.net.ssl.SSLContext');
    SSLContext.init.overload(
        '[Ljavax.net.ssl.KeyManager;',
        '[Ljavax.net.ssl.TrustManager;',
        'java.security.SecureRandom'
    ).implementation = function(keyManager, trustManager, secureRandom) {
        console.log('[+] SSLContext.init() bypassed');
        this.init(keyManager, trustManager, secureRandom);
    };

    // Hook TrustManagerImpl
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            console.log('[+] TrustManagerImpl.verifyChain() bypassed for: ' + host);
            return untrustedChain;
        };
    } catch (e) {
        console.log('[-] TrustManagerImpl not found');
    }

    // Hook OkHttp CertificatePinner
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, peerCertificates) {
            console.log('[+] CertificatePinner.check() bypassed for: ' + hostname);
            return;
        };
    } catch (e) {
        console.log('[-] OkHttp CertificatePinner not found');
    }

    console.log("[*] SSL Unpinning active");
});
