/**
 * Avito Frida Hooks
 *
 * Intercepts session token updates in real-time
 *
 * Usage:
 *   frida -U -f com.avito.android -l frida_avito_hooks.js --no-pause
 *
 * Or attach to running app:
 *   frida -U com.avito.android -l frida_avito_hooks.js
 */

'use strict';

// ============ Configuration ============

const CONFIG = {
    // Server to send tokens (optional)
    serverUrl: null, // "https://your-server.com/api/v1/sessions"
    apiKey: null,

    // Log verbosity
    verbose: true,

    // Auto-save to file
    saveToFile: true,
    filePath: "/data/local/tmp/avito_session.json"
};

// ============ Utilities ============

const log = (tag, msg) => {
    console.log(`[${tag}] ${msg}`);
};

const logVerbose = (tag, msg) => {
    if (CONFIG.verbose) {
        console.log(`[${tag}] ${msg}`);
    }
};

// Send data to host Python script
const sendToHost = (type, data) => {
    send({ type: type, payload: data });
};

// ============ Captured Data ============

let capturedSession = {
    sessionToken: null,
    refreshToken: null,
    fingerprint: null,
    deviceId: null,
    userId: null,
    userHash: null,
    timestamp: null
};

// ============ SharedPreferences Hooks ============

const hookSharedPreferences = () => {
    log("Hook", "Setting up SharedPreferences hooks...");

    Java.perform(() => {
        try {
            const SharedPrefsEditor = Java.use('android.app.SharedPreferencesImpl$EditorImpl');

            // Hook putString to catch token writes
            SharedPrefsEditor.putString.implementation = function(key, value) {
                const result = this.putString(key, value);

                // Keys we care about
                const keyLower = key.toLowerCase();

                if (key === 'session') {
                    log("TOKEN", `New session token: ${value.substring(0, 50)}...`);
                    capturedSession.sessionToken = value;
                    capturedSession.timestamp = Date.now();
                    onSessionUpdate();
                }
                else if (key === 'refresh_token') {
                    log("TOKEN", `New refresh token: ${value}`);
                    capturedSession.refreshToken = value;
                }
                else if (key === 'fpx') {
                    log("TOKEN", `New fingerprint: ${value.substring(0, 50)}...`);
                    capturedSession.fingerprint = value;
                }
                else if (key === 'device_id') {
                    logVerbose("PREFS", `device_id: ${value}`);
                    capturedSession.deviceId = value;
                }
                else if (key === 'profile_hashId') {
                    logVerbose("PREFS", `user_hash: ${value}`);
                    capturedSession.userHash = value;
                }
                else if (key === 'profile_id') {
                    logVerbose("PREFS", `user_id: ${value}`);
                    capturedSession.userId = value;
                }
                else if (keyLower.includes('token') || keyLower.includes('session')) {
                    logVerbose("PREFS", `${key}: ${value ? value.substring(0, 30) + '...' : 'null'}`);
                }

                return result;
            };

            log("Hook", "SharedPreferences hooks installed");

        } catch (e) {
            log("Error", `SharedPreferences hook failed: ${e}`);
        }
    });
};

// ============ OkHttp Interceptor Hooks ============

const hookOkHttp = () => {
    log("Hook", "Setting up OkHttp hooks...");

    Java.perform(() => {
        try {
            // Hook Response to catch session headers
            const Response = Java.use('okhttp3.Response');

            Response.header.overload('java.lang.String').implementation = function(name) {
                const value = this.header(name);

                if (name && value) {
                    const nameLower = name.toLowerCase();
                    if (nameLower.includes('session') || nameLower.includes('token')) {
                        log("HTTP", `Response header ${name}: ${value.substring(0, 50)}...`);
                    }
                }

                return value;
            };

            log("Hook", "OkHttp hooks installed");

        } catch (e) {
            logVerbose("Error", `OkHttp hook failed: ${e}`);
        }
    });
};

// ============ Auth/Session Provider Hooks ============

const hookSessionProvider = () => {
    log("Hook", "Setting up Session Provider hooks...");

    Java.perform(() => {
        // Try to find and hook session-related classes
        const targetClasses = [
            'G0', // SessionHeaderProviderImpl (obfuscated)
            'com.avito.android.auth.SessionManager',
            'com.avito.android.auth.AuthManager',
        ];

        targetClasses.forEach(className => {
            try {
                const cls = Java.use(className);

                // Hook all methods that might return session
                const methods = cls.class.getDeclaredMethods();
                methods.forEach(method => {
                    const methodName = method.getName();
                    const returnType = method.getReturnType().getName();

                    // Methods returning String that might be tokens
                    if (returnType === 'java.lang.String' &&
                        (methodName.includes('get') || methodName.includes('session') || methodName.includes('token'))) {

                        try {
                            cls[methodName].implementation = function() {
                                const result = this[methodName]();
                                if (result && result.length > 50) {
                                    log("SESSION", `${className}.${methodName}(): ${result.substring(0, 50)}...`);
                                }
                                return result;
                            };
                            logVerbose("Hook", `Hooked ${className}.${methodName}()`);
                        } catch (e) {
                            // Method might have parameters, skip
                        }
                    }
                });

            } catch (e) {
                logVerbose("Hook", `Class ${className} not found or failed: ${e.message}`);
            }
        });
    });
};

// ============ Fingerprint Hooks ============

const hookFingerprint = () => {
    log("Hook", "Setting up Fingerprint hooks...");

    Java.perform(() => {
        try {
            const FingerprintService = Java.use('com.avito.security.libfp.FingerprintService');

            // Hook calculateFingerprintV2
            if (FingerprintService.calculateFingerprintV2) {
                FingerprintService.calculateFingerprintV2.implementation = function(timestamp) {
                    const fp = this.calculateFingerprintV2(timestamp);
                    log("FINGERPRINT", `Generated: ${fp.substring(0, 50)}...`);
                    capturedSession.fingerprint = fp;
                    sendToHost('fingerprint', { value: fp, timestamp: timestamp });
                    return fp;
                };
                log("Hook", "Fingerprint hook installed");
            }

        } catch (e) {
            logVerbose("Hook", `Fingerprint hook failed (expected if class obfuscated): ${e.message}`);
        }
    });
};

// ============ Session Update Handler ============

const onSessionUpdate = () => {
    log("UPDATE", "Session updated!");

    // Send to host
    sendToHost('session_update', capturedSession);

    // Save to file if configured
    if (CONFIG.saveToFile) {
        saveSessionToFile();
    }

    // Sync to server if configured
    if (CONFIG.serverUrl) {
        syncToServer();
    }
};

const saveSessionToFile = () => {
    Java.perform(() => {
        try {
            const File = Java.use('java.io.File');
            const FileWriter = Java.use('java.io.FileWriter');

            const json = JSON.stringify(capturedSession, null, 2);

            const file = File.$new(CONFIG.filePath);
            const writer = FileWriter.$new(file);
            writer.write(json);
            writer.close();

            log("SAVE", `Session saved to ${CONFIG.filePath}`);

        } catch (e) {
            log("Error", `Failed to save session: ${e}`);
        }
    });
};

const syncToServer = () => {
    // This would need OkHttp to be used from within the app
    // For now, we send to host and let Python handle it
    log("SYNC", "Sending to host for server sync...");
    sendToHost('sync_request', capturedSession);
};

// ============ Session Dump (on demand) ============

const dumpCurrentSession = () => {
    Java.perform(() => {
        log("DUMP", "Dumping current session from SharedPreferences...");

        try {
            const Context = Java.use('android.content.Context');
            const ActivityThread = Java.use('android.app.ActivityThread');

            const context = ActivityThread.currentApplication().getApplicationContext();
            const prefs = context.getSharedPreferences('com.avito.android_preferences', 0);

            capturedSession.sessionToken = prefs.getString('session', null);
            capturedSession.refreshToken = prefs.getString('refresh_token', null);
            capturedSession.fingerprint = prefs.getString('fpx', null);
            capturedSession.deviceId = prefs.getString('device_id', null);
            capturedSession.userId = prefs.getString('profile_id', null);
            capturedSession.userHash = prefs.getString('profile_hashId', null);
            capturedSession.timestamp = Date.now();

            log("DUMP", `Session token: ${capturedSession.sessionToken ? capturedSession.sessionToken.substring(0, 50) + '...' : 'null'}`);
            log("DUMP", `Fingerprint: ${capturedSession.fingerprint ? capturedSession.fingerprint.substring(0, 50) + '...' : 'null'}`);
            log("DUMP", `Refresh token: ${capturedSession.refreshToken}`);
            log("DUMP", `User ID: ${capturedSession.userId}`);

            sendToHost('session_dump', capturedSession);

        } catch (e) {
            log("Error", `Dump failed: ${e}`);
        }
    });
};

// ============ RPC Exports ============

rpc.exports = {
    // Dump current session
    dump: function() {
        dumpCurrentSession();
        return capturedSession;
    },

    // Get captured session
    getSession: function() {
        return capturedSession;
    },

    // Force sync
    sync: function() {
        onSessionUpdate();
    },

    // Set server config
    setServer: function(url, apiKey) {
        CONFIG.serverUrl = url;
        CONFIG.apiKey = apiKey;
        log("CONFIG", `Server set to ${url}`);
    }
};

// ============ Main ============

log("Avito", "Frida hooks loading...");

Java.perform(() => {
    log("Avito", "Java VM ready");

    // Install hooks
    hookSharedPreferences();
    hookOkHttp();
    hookSessionProvider();
    hookFingerprint();

    // Dump initial session
    setTimeout(() => {
        dumpCurrentSession();
    }, 2000);

    log("Avito", "All hooks installed! Monitoring for token updates...");
});
