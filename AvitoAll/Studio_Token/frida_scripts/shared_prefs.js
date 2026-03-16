/**
 * SharedPreferences Reader Script
 *
 * Monitors reads/writes to SharedPreferences
 * Useful for finding where Avito stores session tokens
 *
 * Usage:
 *   frida -U -f com.avito.android -l shared_prefs.js --no-pause
 */

Java.perform(function() {
    console.log("[*] SharedPreferences monitor loaded");

    try {
        var SharedPrefsImpl = Java.use('android.app.SharedPreferencesImpl');

        // Hook getString
        SharedPrefsImpl.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
            var value = this.getString(key, defValue);

            // Log interesting keys
            if (key.includes('session') || key.includes('token') || key.includes('fingerprint') || key.includes('device')) {
                console.log('[SharedPrefs] GET: ' + key + ' = ' + (value ? value.substring(0, 40) + '...' : 'null'));
            }

            return value;
        };

        // Hook putString
        SharedPrefsImpl.EditorImpl = Java.use('android.app.SharedPreferencesImpl$EditorImpl');
        SharedPrefsImpl.EditorImpl.putString.implementation = function(key, value) {
            if (key.includes('session') || key.includes('token') || key.includes('fingerprint') || key.includes('device')) {
                console.log('[SharedPrefs] PUT: ' + key + ' = ' + (value ? value.substring(0, 40) + '...' : 'null'));
            }

            return this.putString(key, value);
        };

        console.log("[+] SharedPreferences hooked");
    } catch (e) {
        console.log('[-] Failed to hook SharedPreferences: ' + e);
    }

    // Hook specific Avito preferences file
    try {
        var Context = Java.use('android.content.Context');
        Context.getSharedPreferences.overload('java.lang.String', 'int').implementation = function(name, mode) {
            if (name.includes('avito')) {
                console.log('[SharedPrefs] Opening: ' + name);
            }
            return this.getSharedPreferences(name, mode);
        };
    } catch (e) {
        console.log('[-] Failed to hook getSharedPreferences: ' + e);
    }

    console.log("[*] SharedPreferences monitor active");
});
