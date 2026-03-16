/**
 * grab_token.js — Frida script to extract Avito tokens from SharedPreferences.
 *
 * Attaches to a running Avito process and reads the session/refresh tokens
 * from SharedPreferences XML files.
 *
 * Output: prints TOKEN_DATA|{json} to stdout for the agent to parse.
 *
 * Usage:
 *   frida -U --attach-name com.avito.android -l grab_token.js --no-pause -q
 */

'use strict';

Java.perform(function() {
    console.log('[*] grab_token.js — extracting tokens...');

    try {
        var context = Java.use('android.app.ActivityThread').currentApplication().getApplicationContext();
        var userId = Java.use('android.os.Process').myUserHandle().hashCode();

        // ── Method 1: Read SharedPreferences directly ────────

        var result = {
            session_token: null,
            refresh_token: null,
            fingerprint: null,
            device_id: null,
            remote_device_id: null,
            user_hash: null,
            cookies: {},
        };

        // Avito stores tokens in several SharedPreferences files
        var prefNames = [
            'auth_prefs',
            'session_prefs',
            'avito_prefs',
            'user_session',
            // Generic default
            context.getPackageName() + '_preferences',
        ];

        // Known token keys
        var tokenKeys = {
            'session_token': ['session_token', 'sessionToken', 'access_token', 'accessToken', 'token'],
            'refresh_token': ['refresh_token', 'refreshToken'],
            'fingerprint': ['fingerprint', 'device_fingerprint', 'f'],
            'device_id': ['device_id', 'deviceId', 'x_device_id'],
            'remote_device_id': ['remote_device_id', 'remoteDeviceId'],
            'user_hash': ['user_hash', 'userHash'],
        };

        var SharedPreferences = Java.use('android.content.Context');

        prefNames.forEach(function(prefName) {
            try {
                var prefs = context.getSharedPreferences(prefName, 0);
                var allEntries = prefs.getAll();
                var iterator = allEntries.entrySet().iterator();

                while (iterator.hasNext()) {
                    var entry = iterator.next();
                    var key = entry.getKey().toString();
                    var value = entry.getValue();

                    if (value === null) continue;
                    var strValue = value.toString();

                    // Check against known token keys
                    for (var field in tokenKeys) {
                        var aliases = tokenKeys[field];
                        for (var i = 0; i < aliases.length; i++) {
                            if (key.toLowerCase() === aliases[i].toLowerCase() ||
                                key.toLowerCase().indexOf(aliases[i].toLowerCase()) !== -1) {
                                if (!result[field] && strValue.length > 5) {
                                    result[field] = strValue;
                                }
                            }
                        }
                    }

                    // Check for cookie-like values
                    if (key.toLowerCase().indexOf('cookie') !== -1 ||
                        key === '1f_uid' || key === 'u' || key === 'sessid') {
                        result.cookies[key] = strValue;
                    }
                }
            } catch(e) {
                // SharedPreferences file doesn't exist, skip
            }
        });

        // ── Method 2: Read XML files directly (fallback) ────

        if (!result.session_token) {
            console.log('[*] SharedPreferences method failed, trying XML files...');

            var File = Java.use('java.io.File');
            var dataDir = context.getDataDir().getAbsolutePath();
            var prefsDir = dataDir + '/shared_prefs/';

            try {
                var dir = File.$new(prefsDir);
                var files = dir.listFiles();

                if (files) {
                    for (var f = 0; f < files.length; f++) {
                        var fileName = files[f].getName();
                        if (!fileName.endsWith('.xml')) continue;

                        try {
                            var fis = Java.use('java.io.FileInputStream').$new(files[f]);
                            var bytes = Java.array('byte', new Array(Math.min(files[f].length(), 65536)).fill(0));
                            fis.read(bytes);
                            fis.close();

                            var content = Java.use('java.lang.String').$new(bytes).toString();

                            // Look for JWT-like strings (eyJ...)
                            var jwtMatch = content.match(/eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
                            if (jwtMatch && !result.session_token) {
                                result.session_token = jwtMatch[0];
                                console.log('[+] Found JWT in ' + fileName);
                            }

                            // Look for refresh token (32 hex chars)
                            var refreshMatch = content.match(/[a-f0-9]{32}/);
                            if (refreshMatch && !result.refresh_token) {
                                result.refresh_token = refreshMatch[0];
                            }

                            // Look for fingerprint (A2.xxx)
                            var fpMatch = content.match(/A2\.[a-f0-9]{20,}/);
                            if (fpMatch && !result.fingerprint) {
                                result.fingerprint = fpMatch[0];
                            }
                        } catch(e) {
                            // Can't read file, skip
                        }
                    }
                }
            } catch(e) {
                console.log('[-] XML fallback failed: ' + e);
            }
        }

        // ── Method 3: Hook network interceptor (last resort) ─

        if (!result.session_token) {
            console.log('[*] No tokens found in prefs/XML. Hooking OkHttp to intercept next request...');

            try {
                var OkHttpClient = Java.use('okhttp3.OkHttpClient');
                var Interceptor = Java.use('okhttp3.Interceptor');
                var Chain = Java.use('okhttp3.Interceptor$Chain');

                // Hook addInterceptor to sniff headers
                var RealCall = Java.use('okhttp3.internal.connection.RealCall');
                RealCall.getResponseWithInterceptorChain.implementation = function() {
                    var response = this.getResponseWithInterceptorChain();
                    try {
                        var request = response.request();
                        var sessionHeader = request.header('X-Session');
                        if (sessionHeader && !result.session_token) {
                            result.session_token = sessionHeader;
                            console.log('[+] Intercepted X-Session from OkHttp');
                            // Output immediately
                            console.log('TOKEN_DATA|' + JSON.stringify(result));
                        }
                    } catch(e) {}
                    return response;
                };

                console.log('[*] OkHttp hook installed, waiting for network request...');
                // Wait a bit for a network request to happen
                // The agent will timeout if nothing comes
            } catch(e) {
                console.log('[-] OkHttp hook failed: ' + e);
            }
        }

        // ── Output result ────────────────────────────────────

        if (result.session_token) {
            console.log('[+] Tokens extracted successfully');
            console.log('TOKEN_DATA|' + JSON.stringify(result));
        } else {
            console.log('[-] No tokens found');
            console.log('TOKEN_DATA|' + JSON.stringify(result));
        }

    } catch(e) {
        console.log('[-] Fatal error: ' + e);
        console.log('TOKEN_DATA|{"error":"' + e.toString().replace(/"/g, '\\"') + '"}');
    }
});
