// Universal SSL Pinning Bypass for Android
// With delayed Java.perform

setTimeout(function() {
    Java.perform(function() {
        console.log("[*] SSL Pinning Bypass loaded");

        // 1. Bypass OkHttp CertificatePinner
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, peerCertificates) {
                console.log("[+] OkHttp bypassed: " + hostname);
                return;
            };
            CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, peerCertificates) {
                console.log("[+] OkHttp bypassed: " + hostname);
                return;
            };
            console.log("[+] OkHttp CertificatePinner hooked");
        } catch(e) {
            console.log("[-] OkHttp: " + e);
        }

        // 2. Bypass TrustManagerImpl (Android)
        try {
            var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
            TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
                console.log("[+] TrustManager bypassed: " + host);
                return untrustedChain;
            };
            console.log("[+] TrustManagerImpl hooked");
        } catch(e) {
            console.log("[-] TrustManagerImpl: " + e);
        }

        // 3. Avito CertificatePinning interceptor
        try {
            var avitoPin = Java.use("com.avito.android.certificate_pinning.domain.e");
            avitoPin.intercept.implementation = function(chain) {
                console.log("[+] Avito pinning bypassed");
                return chain.proceed(chain.request());
            };
            console.log("[+] Avito certificate_pinning hooked");
        } catch(e) {
            console.log("[-] Avito pinning: " + e);
        }

        // 4. Avito CertificatePinningInterceptorImpl
        try {
            var avitoPin2 = Java.use("com.avito.android.remote.interceptor.C34315x");
            avitoPin2.intercept.implementation = function(chain) {
                console.log("[+] Avito SSL interceptor bypassed");
                return chain.proceed(chain.request());
            };
            console.log("[+] Avito SSL interceptor hooked");
        } catch(e) {
            console.log("[-] Avito interceptor: " + e);
        }

        // 5. Generic SSLContext bypass
        try {
            var TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var SSLContext = Java.use('javax.net.ssl.SSLContext');

            var TrustAll = Java.registerClass({
                name: 'dev.bypass.TrustAll',
                implements: [TrustManager],
                methods: {
                    checkClientTrusted: function(chain, authType) {},
                    checkServerTrusted: function(chain, authType) {},
                    getAcceptedIssuers: function() { return []; }
                }
            });

            var TrustAllArray = [TrustAll.$new()];

            SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
                console.log("[+] SSLContext.init bypassed");
                this.init(km, TrustAllArray, sr);
            };
            console.log("[+] SSLContext hooked");
        } catch(e) {
            console.log("[-] SSLContext: " + e);
        }

        // 6. Force proxy for OkHttpClient
        try {
            var Proxy = Java.use('java.net.Proxy');
            var ProxyType = Java.use('java.net.Proxy$Type');
            var InetSocketAddress = Java.use('java.net.InetSocketAddress');

            var proxyAddress = InetSocketAddress.$new("127.0.0.1", 8082);
            var httpProxy = Proxy.$new(ProxyType.HTTP.value, proxyAddress);

            // Hook OkHttpClient.Builder.proxy() to always set our proxy
            var OkHttpClientBuilder = Java.use('okhttp3.OkHttpClient$Builder');
            var originalProxy = OkHttpClientBuilder.proxy;
            OkHttpClientBuilder.proxy.implementation = function(proxy) {
                console.log("[+] OkHttpClient.Builder.proxy() - forcing our proxy");
                return originalProxy.call(this, httpProxy);
            };
            console.log("[+] OkHttpClient proxy hooked");
        } catch(e) {
            console.log("[-] Proxy injection: " + e);
        }

        // 7. Hook URL.openConnection to add proxy
        try {
            var URL = Java.use('java.net.URL');
            URL.openConnection.overload().implementation = function() {
                console.log("[+] URL.openConnection() -> using proxy for: " + this.toString());
                var Proxy = Java.use('java.net.Proxy');
                var ProxyType = Java.use('java.net.Proxy$Type');
                var InetSocketAddress = Java.use('java.net.InetSocketAddress');
                var proxyAddress = InetSocketAddress.$new("127.0.0.1", 8082);
                var httpProxy = Proxy.$new(ProxyType.HTTP.value, proxyAddress);
                return this.openConnection(httpProxy);
            };
            console.log("[+] URL.openConnection hooked");
        } catch(e) {
            console.log("[-] URL.openConnection: " + e);
        }

        console.log("\n[*] SSL Bypass + Proxy READY!");
        console.log("[*] Proxy: 127.0.0.1:8082");
        console.log("[*] Try to login in Avito now\n");
    });
}, 1000);
