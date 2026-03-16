// Chrome Cookie Capture for Avito
// Captures sessid and other auth cookies from Chrome browser

setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Chrome Cookie Capture v1.0\n");

        // ============ CookieManager Hook ============
        // Main Android API for WebView cookies

        try {
            var CookieManager = Java.use("android.webkit.CookieManager");

            CookieManager.getCookie.overload('java.lang.String').implementation = function(url) {
                var cookies = this.getCookie(url);

                if (url && url.toLowerCase().indexOf("avito") !== -1) {
                    console.log("\n[COOKIE GET] " + url);
                    if (cookies) {
                        console.log("[COOKIES] " + cookies);

                        // Extract sessid
                        var sessidMatch = cookies.match(/sessid=([^;]+)/);
                        if (sessidMatch) {
                            console.log("\n========================================");
                            console.log("[SESSID FOUND] " + sessidMatch[1]);
                            console.log("========================================\n");
                        }
                    }
                }
                return cookies;
            };

            console.log("[+] CookieManager.getCookie hooked");
        } catch(e) {
            console.log("[-] CookieManager hook failed: " + e);
        }

        // ============ setCookie Hook ============

        try {
            var CookieManager = Java.use("android.webkit.CookieManager");

            CookieManager.setCookie.overload('java.lang.String', 'java.lang.String').implementation = function(url, value) {
                if (url && url.toLowerCase().indexOf("avito") !== -1) {
                    console.log("\n[COOKIE SET] " + url);
                    console.log("[VALUE] " + value);

                    if (value && value.toLowerCase().indexOf("sessid") !== -1) {
                        var sessidMatch = value.match(/sessid=([^;]+)/);
                        if (sessidMatch) {
                            console.log("\n========================================");
                            console.log("[SESSID SET] " + sessidMatch[1]);
                            console.log("========================================\n");
                        }
                    }
                }
                return this.setCookie(url, value);
            };

            console.log("[+] CookieManager.setCookie hooked");
        } catch(e) {}

        // ============ HTTP Headers Hook (OkHttp in Chrome) ============

        try {
            var URL = Java.use("java.net.URL");
            var HttpURLConnection = Java.use("java.net.HttpURLConnection");

            HttpURLConnection.setRequestProperty.implementation = function(key, value) {
                if (key && key.toLowerCase() === "cookie" && value && value.indexOf("avito") !== -1) {
                    console.log("\n[HTTP COOKIE] " + value);

                    var sessidMatch = value.match(/sessid=([^;]+)/);
                    if (sessidMatch) {
                        console.log("\n========================================");
                        console.log("[SESSID IN REQUEST] " + sessidMatch[1]);
                        console.log("========================================\n");
                    }
                }
                return this.setRequestProperty(key, value);
            };

            console.log("[+] HttpURLConnection hooked");
        } catch(e) {}

        // ============ Cronet (Chrome's network stack) ============

        try {
            var CronetUrlRequest = Java.use("org.chromium.net.impl.CronetUrlRequest");

            CronetUrlRequest.start.implementation = function() {
                try {
                    var url = this.getCurrentUrl();
                    if (url && url.indexOf("avito") !== -1) {
                        console.log("\n[CRONET REQUEST] " + url);
                    }
                } catch(e) {}
                return this.start();
            };

            console.log("[+] Cronet hooked");
        } catch(e) {}

        // ============ WebView loadUrl Hook ============

        try {
            var WebView = Java.use("android.webkit.WebView");

            WebView.loadUrl.overload('java.lang.String').implementation = function(url) {
                if (url && url.toLowerCase().indexOf("avito") !== -1) {
                    console.log("\n[WEBVIEW LOAD] " + url);

                    // Try to get cookies for this URL
                    try {
                        var cm = Java.use("android.webkit.CookieManager").getInstance();
                        var cookies = cm.getCookie(url);
                        if (cookies) {
                            console.log("[WEBVIEW COOKIES] " + cookies);

                            var sessidMatch = cookies.match(/sessid=([^;]+)/);
                            if (sessidMatch) {
                                console.log("\n========================================");
                                console.log("[SESSID] " + sessidMatch[1]);
                                console.log("========================================\n");
                            }
                        }
                    } catch(e) {}
                }
                return this.loadUrl(url);
            };

            console.log("[+] WebView.loadUrl hooked");
        } catch(e) {}

        // ============ Dump all Avito cookies on demand ============

        // Create a function to dump cookies
        var dumpAvitoCookies = function() {
            try {
                var cm = Java.use("android.webkit.CookieManager").getInstance();
                var urls = [
                    "https://www.avito.ru",
                    "https://avito.ru",
                    "https://m.avito.ru",
                    "https://api.avito.ru",
                    "https://app.avito.ru",
                    "https://socket.avito.ru"
                ];

                console.log("\n============ AVITO COOKIES DUMP ============");

                urls.forEach(function(url) {
                    var cookies = cm.getCookie(url);
                    if (cookies) {
                        console.log("\n[" + url + "]");
                        console.log(cookies);

                        var sessidMatch = cookies.match(/sessid=([^;]+)/);
                        if (sessidMatch) {
                            console.log("\n>>> SESSID: " + sessidMatch[1]);
                        }
                    }
                });

                console.log("\n=============================================\n");
            } catch(e) {
                console.log("[-] Dump error: " + e);
            }
        };

        // Auto-dump every 10 seconds
        setInterval(function() {
            Java.perform(function() {
                dumpAvitoCookies();
            });
        }, 10000);

        // ============ Chrome SharedPreferences ============

        try {
            var SharedPreferencesImpl = Java.use("android.app.SharedPreferencesImpl");

            SharedPreferencesImpl.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
                var result = this.getString(key, defValue);

                var keyLower = key.toLowerCase();
                if (keyLower.indexOf("cookie") !== -1 ||
                    keyLower.indexOf("session") !== -1 ||
                    keyLower.indexOf("auth") !== -1 ||
                    keyLower.indexOf("avito") !== -1) {
                    console.log("\n[PREF] " + key + " = " + result);
                }

                return result;
            };

            console.log("[+] SharedPreferences hooked");
        } catch(e) {}

        console.log("\n[*] Cookie Capture ready!");
        console.log("[*] Open avito.ru in Chrome and login");
        console.log("[*] Cookies will be dumped every 10 seconds\n");

        // Initial dump
        setTimeout(function() {
            Java.perform(function() {
                dumpAvitoCookies();
            });
        }, 3000);
    });
}, 1000);
