// Frida script to intercept OkHttp headers in Avito
// Usage: frida -U -f com.avito.android -l hook_headers.js --no-pause

Java.perform(function() {
    console.log("[*] Starting OkHttp headers interception...");

    // Hook OkHttp Request.Builder
    var RequestBuilder = Java.use("okhttp3.Request$Builder");

    RequestBuilder.addHeader.implementation = function(name, value) {
        console.log("[Header] " + name + ": " + value);
        return this.addHeader(name, value);
    };

    RequestBuilder.header.implementation = function(name, value) {
        console.log("[Header] " + name + ": " + value);
        return this.header(name, value);
    };

    // Hook Request to see full request
    var Request = Java.use("okhttp3.Request");
    Request.headers.implementation = function() {
        var headers = this.headers();
        console.log("\n[*] ========== REQUEST ==========");
        console.log("[URL] " + this.url().toString());
        console.log("[Method] " + this.method());

        var headerNames = headers.names();
        var iterator = headerNames.iterator();
        while(iterator.hasNext()) {
            var name = iterator.next();
            console.log("[H] " + name + ": " + headers.get(name));
        }
        console.log("[*] ================================\n");
        return headers;
    };

    // Hook Response to see response headers
    var Response = Java.use("okhttp3.Response");
    Response.headers.implementation = function() {
        var headers = this.headers();
        var req = this.request();
        console.log("\n[*] ========== RESPONSE ==========");
        console.log("[URL] " + req.url().toString());
        console.log("[Code] " + this.code());

        var headerNames = headers.names();
        var iterator = headerNames.iterator();
        while(iterator.hasNext()) {
            var name = iterator.next();
            console.log("[RH] " + name + ": " + headers.get(name));
        }
        console.log("[*] ================================\n");
        return headers;
    };

    // Hook Interceptor chain to see all interceptors
    try {
        var RealInterceptorChain = Java.use("okhttp3.internal.http.RealInterceptorChain");
        RealInterceptorChain.proceed.overload('okhttp3.Request').implementation = function(request) {
            var url = request.url().toString();
            if (url.indexOf("avito") !== -1) {
                console.log("\n[INTERCEPT] " + request.method() + " " + url);
                var headers = request.headers();
                var size = headers.size();
                for (var i = 0; i < size; i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }
            return this.proceed(request);
        };
    } catch(e) {
        console.log("[!] RealInterceptorChain hook failed: " + e);
    }

    console.log("[*] Hooks installed. Open Avito app...");
});
