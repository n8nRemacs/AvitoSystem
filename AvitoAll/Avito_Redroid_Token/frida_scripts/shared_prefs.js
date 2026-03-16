/**
 * SharedPreferences Reader for Avito
 *
 * Reads and displays all SharedPreferences data
 * Useful for finding token storage keys
 */

Java.perform(function() {
    console.log('[*] SharedPreferences reader loaded');

    try {
        // Get application context
        var ActivityThread = Java.use('android.app.ActivityThread');
        var context = ActivityThread.currentApplication().getApplicationContext();

        // Get SharedPreferences
        var prefsName = 'com.avito.android_preferences';
        var prefs = context.getSharedPreferences(prefsName, 0);

        // Get all data
        var allData = prefs.getAll();
        var keySet = allData.keySet();
        var iterator = keySet.iterator();

        console.log('\n========================================');
        console.log('SharedPreferences: ' + prefsName);
        console.log('========================================\n');

        var tokenCount = 0;

        while (iterator.hasNext()) {
            var key = iterator.next();
            var value = allData.get(key);

            // Convert value to string
            var valueStr = '';
            try {
                valueStr = value.toString();
            } catch (e) {
                valueStr = '[Cannot convert to string]';
            }

            // Highlight important keys
            var keyLower = key.toLowerCase();
            var isImportant = (
                keyLower.includes('token') ||
                keyLower.includes('session') ||
                keyLower.includes('fingerprint') ||
                keyLower.includes('user') ||
                keyLower.includes('device') ||
                key === 'f'
            );

            if (isImportant) {
                console.log('[!] ' + key + ':');

                // Truncate long values for readability
                if (valueStr.length > 100) {
                    console.log('    ' + valueStr.substring(0, 100) + '...');
                    console.log('    Length: ' + valueStr.length + ' chars');
                } else {
                    console.log('    ' + valueStr);
                }

                tokenCount++;
            } else {
                // Just show key name for non-important data
                console.log(key + ': [' + valueStr.length + ' chars]');
            }
        }

        console.log('\n========================================');
        console.log('Found ' + tokenCount + ' token-related keys');
        console.log('========================================\n');

    } catch (e) {
        console.log('[-] Error reading SharedPreferences: ' + e);
        console.log('Stack trace:');
        console.log(e.stack);
    }

    // Hook getString to monitor reads
    try {
        var SharedPrefsImpl = Java.use('android.app.SharedPreferencesImpl');

        SharedPrefsImpl.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
            var value = this.getString(key, defValue);

            // Log important key reads
            var keyLower = key.toLowerCase();
            if (keyLower.includes('token') ||
                keyLower.includes('session') ||
                keyLower.includes('fingerprint') ||
                key === 'f') {

                console.log('[SharedPreferences READ]');
                console.log('Key: ' + key);

                if (value && value.length > 100) {
                    console.log('Value: ' + value.substring(0, 100) + '...');
                } else {
                    console.log('Value: ' + value);
                }
            }

            return value;
        };

        console.log('[+] getString() hooked for monitoring');

    } catch (e) {
        console.log('[-] Could not hook getString: ' + e);
    }

    console.log('[*] SharedPreferences reader ready!');
});
