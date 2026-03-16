/**
 * HTTP Headers Capture Script
 *
 * Captures HTTP/HTTPS requests and responses including headers
 * Useful for extracting session tokens, fingerprints, and device IDs
 *
 * Usage:
 *   frida -U -f com.avito.android -l http_capture.js --no-pause
 */

Java.perform(function() {
    console.log("[*] HTTP Capture script loaded");

    // Hook OkHttp Request
    try {
        var Request = Java.use('okhttp3.Request');
        var RequestBuilder = Java.use('okhttp3.Request$Builder');

        RequestBuilder.build.implementation = function() {
            var request = this.build();
            var url = request.url().toString();
            var method = request.method();

            console.log('\n[HTTP] ' + method + ' ' + url);

            // Get headers
            var headers = request.headers();
            var headerNames = headers.names();
            var iterator = headerNames.iterator();

            console.log('[HEADERS]:');
            while (iterator.hasNext()) {
                var name = iterator.next();
                var value = headers.get(name);

                // Highlight important headers
                if (name === 'X-Session' || name === 'f' || name === 'X-DeviceId') {
                    console.log('  ' + name + ': ' + value + ' ⭐');
                } else {
                    console.log('  ' + name + ': ' + value);
                }
            }

            return request;
        };

        console.log("[+] OkHttp Request hooked");
    } catch (e) {
        console.log('[-] Failed to hook OkHttp Request: ' + e);
    }

    // Hook HttpURLConnection
    try {
        var HttpURLConnection = Java.use('java.net.HttpURLConnection');

        HttpURLConnection.setRequestProperty.implementation = function(key, value) {
            if (key === 'X-Session' || key === 'f' || key === 'X-DeviceId') {
                console.log('[HEADER] ' + key + ': ' + value + ' ⭐');
            }
            return this.setRequestProperty(key, value);
        };

        console.log("[+] HttpURLConnection hooked");
    } catch (e) {
        console.log('[-] Failed to hook HttpURLConnection: ' + e);
    }

    console.log("[*] HTTP Capture active");
});
