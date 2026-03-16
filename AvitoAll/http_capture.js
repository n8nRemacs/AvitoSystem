/*
 * HTTP Capture via OkHttp hooks
 * Captures all requests/responses without proxy
 */

Java.perform(function() {
    console.log("[*] HTTP Capture loaded");

    // Hook OkHttp3 RealCall.execute() and enqueue()
    try {
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');

        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();
            var method = request.method();

            console.log("\n========== REQUEST ==========");
            console.log("[>] " + method + " " + url);

            // Print headers
            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log("[H] " + headers.name(i) + ": " + headers.value(i));
            }

            // Print body for POST/PUT
            var body = request.body();
            if (body != null && (method === "POST" || method === "PUT")) {
                try {
                    var Buffer = Java.use('okio.Buffer');
                    var buffer = Buffer.$new();
                    body.writeTo(buffer);
                    var bodyStr = buffer.readUtf8();
                    if (bodyStr.length < 5000) {
                        console.log("[B] " + bodyStr);
                    } else {
                        console.log("[B] (body too large: " + bodyStr.length + " bytes)");
                    }
                } catch(e) {
                    console.log("[B] (cannot read body)");
                }
            }

            // Execute and capture response
            var response = this.execute();

            console.log("\n========== RESPONSE ==========");
            console.log("[<] " + response.code() + " " + response.message());

            // Print response headers
            var respHeaders = response.headers();
            for (var i = 0; i < respHeaders.size(); i++) {
                console.log("[H] " + respHeaders.name(i) + ": " + respHeaders.value(i));
            }

            // Print response body (need to clone it)
            try {
                var respBody = response.peekBody(Java.use('java.lang.Long').MAX_VALUE.value);
                var respStr = respBody.string();
                if (respStr.length < 5000) {
                    console.log("[B] " + respStr);
                } else {
                    console.log("[B] (response too large: " + respStr.length + " bytes)");
                }
            } catch(e) {
                console.log("[B] (cannot read response body)");
            }

            console.log("==============================\n");

            return response;
        };

        console.log("[+] RealCall.execute hooked");
    } catch(e) {
        console.log("[-] RealCall: " + e);
    }

    // Hook async calls too
    try {
        var Callback = Java.use('okhttp3.Callback');
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');

        RealCall.enqueue.implementation = function(callback) {
            var request = this.request();
            var url = request.url().toString();
            var method = request.method();

            console.log("\n========== ASYNC REQUEST ==========");
            console.log("[>] " + method + " " + url);

            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log("[H] " + headers.name(i) + ": " + headers.value(i));
            }

            var body = request.body();
            if (body != null && (method === "POST" || method === "PUT")) {
                try {
                    var Buffer = Java.use('okio.Buffer');
                    var buffer = Buffer.$new();
                    body.writeTo(buffer);
                    var bodyStr = buffer.readUtf8();
                    if (bodyStr.length < 5000) {
                        console.log("[B] " + bodyStr);
                    }
                } catch(e) {}
            }

            console.log("====================================\n");

            return this.enqueue(callback);
        };

        console.log("[+] RealCall.enqueue hooked");
    } catch(e) {
        console.log("[-] RealCall.enqueue: " + e);
    }

    // Also hook Response.Builder to capture responses for async
    try {
        var ResponseBuilder = Java.use('okhttp3.Response$Builder');
        ResponseBuilder.build.implementation = function() {
            var response = this.build();
            var request = response.request();
            var url = request.url().toString();

            if (url.includes("avito") || url.includes("vk.")) {
                console.log("\n========== ASYNC RESPONSE ==========");
                console.log("[<] " + response.code() + " " + url);
                try {
                    var respBody = response.peekBody(Java.use('java.lang.Long').MAX_VALUE.value);
                    var respStr = respBody.string();
                    if (respStr.length < 3000) {
                        console.log("[B] " + respStr);
                    }
                } catch(e) {}
                console.log("=====================================\n");
            }

            return response;
        };
        console.log("[+] Response.Builder hooked");
    } catch(e) {
        console.log("[-] Response.Builder: " + e);
    }

    console.log("[*] HTTP Capture READY!");
    console.log("[*] Now login to Avito to capture auth flow");
});
