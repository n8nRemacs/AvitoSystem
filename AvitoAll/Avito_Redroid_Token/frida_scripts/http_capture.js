/**
 * HTTP Capture Script for Avito
 *
 * Captures HTTP/HTTPS requests and responses
 * Focuses on authentication headers and tokens
 */

Java.perform(function() {
    console.log('[*] HTTP Capture script loaded');

    try {
        // Hook OkHttp3 (used by Avito)
        var OkHttpClient = Java.use('okhttp3.OkHttpClient');
        var Request = Java.use('okhttp3.Request');
        var Response = Java.use('okhttp3.Response');

        // Hook Request.Builder.build()
        var RequestBuilder = Java.use('okhttp3.Request$Builder');
        RequestBuilder.build.implementation = function() {
            var request = this.build();

            var url = request.url().toString();
            var method = request.method();

            // Only log Avito API requests
            if (url.includes('avito.ru')) {
                console.log('\n[HTTP REQUEST]');
                console.log('URL: ' + url);
                console.log('Method: ' + method);

                // Get headers
                var headers = request.headers();
                var headerNames = headers.names().toArray();

                console.log('Headers:');
                for (var i = 0; i < headerNames.length; i++) {
                    var name = headerNames[i];
                    var value = headers.get(name);

                    // Highlight important headers
                    if (name === 'X-Session' || name === 'f' || name === 'X-DeviceId' ||
                        name === 'Authorization' || name === 'Cookie') {
                        console.log('  [!] ' + name + ': ' + value);
                    } else {
                        console.log('  ' + name + ': ' + value);
                    }
                }
            }

            return request;
        };

        // Hook Response to capture tokens in responses
        var ResponseBuilder = Java.use('okhttp3.Response$Builder');
        ResponseBuilder.build.implementation = function() {
            var response = this.build();

            var url = response.request().url().toString();

            // Check for auth/token endpoints
            if (url.includes('avito.ru') &&
                (url.includes('/auth/') || url.includes('/token') || url.includes('/session'))) {

                console.log('\n[HTTP RESPONSE]');
                console.log('URL: ' + url);
                console.log('Status: ' + response.code());

                // Try to read response body
                try {
                    var responseBody = response.peekBody(10000);
                    var bodyString = responseBody.string();

                    console.log('Body:');
                    console.log(bodyString.substring(0, 500)); // First 500 chars

                    // Try to parse as JSON
                    try {
                        var jsonObj = JSON.parse(bodyString);

                        // Look for tokens
                        if (jsonObj.access_token) {
                            console.log('[!] ACCESS TOKEN FOUND: ' + jsonObj.access_token);
                        }
                        if (jsonObj.refresh_token) {
                            console.log('[!] REFRESH TOKEN FOUND: ' + jsonObj.refresh_token);
                        }
                        if (jsonObj.session_token) {
                            console.log('[!] SESSION TOKEN FOUND: ' + jsonObj.session_token);
                        }
                    } catch (e) {
                        // Not JSON or parse error
                    }
                } catch (e) {
                    console.log('[-] Could not read response body: ' + e);
                }
            }

            return response;
        };

        console.log('[+] OkHttp3 hooked');

    } catch (e) {
        console.log('[-] Error hooking OkHttp: ' + e);
    }

    // Hook SharedPreferences to catch token writes
    try {
        var SharedPrefsImpl = Java.use('android.app.SharedPreferencesImpl');
        var Editor = Java.use('android.app.SharedPreferencesImpl$EditorImpl');

        Editor.putString.implementation = function(key, value) {
            // Check for token-related keys
            if (key.toLowerCase().includes('token') ||
                key.toLowerCase().includes('session') ||
                key.toLowerCase().includes('fingerprint') ||
                key === 'f') {

                console.log('\n[SharedPreferences WRITE]');
                console.log('Key: ' + key);
                console.log('Value: ' + value);
            }

            return this.putString(key, value);
        };

        console.log('[+] SharedPreferences hooked');

    } catch (e) {
        console.log('[-] Could not hook SharedPreferences: ' + e);
    }

    console.log('[*] HTTP capture active!');
});
