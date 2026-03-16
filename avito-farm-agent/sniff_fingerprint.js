/**
 * sniff_fingerprint.js — Frida script for reconnaissance of Avito's device fingerprinting.
 *
 * Purpose: Hook all major Android system APIs that apps commonly use for device
 * fingerprinting. Log which ones Avito actually calls, when, and what values it reads.
 *
 * Usage:
 *   frida -U -f com.avito.android -l sniff_fingerprint.js --no-pause
 *
 * Output: Each hooked call prints a JSON line to stdout:
 *   {"api":"TelephonyManager","method":"getDeviceId","value":"...","stack":"..."}
 *
 * After running, analyze output to determine the minimum set of APIs to spoof.
 */

'use strict';

// ── Logging helper ───────────────────────────────────

var logged = {};

function log(api, method, value, extra) {
    var key = api + '.' + method;
    var entry = {
        api: api,
        method: method,
        value: value !== null && value !== undefined ? value.toString() : null,
        timestamp: Date.now(),
    };
    if (extra) entry.extra = extra;

    // Log first call with stack trace, subsequent without
    if (!logged[key]) {
        logged[key] = 0;
        try {
            entry.stack = Java.use('java.lang.Thread').currentThread().getStackTrace()
                .slice(0, 10).map(function(f) { return f.toString(); });
        } catch(e) {}
    }
    logged[key]++;
    entry.call_count = logged[key];

    console.log('SNIFF|' + JSON.stringify(entry));
}


// ── Wait for Java VM ─────────────────────────────────

Java.perform(function() {
    console.log('[*] sniff_fingerprint.js loaded, hooking APIs...');


    // ══════════════════════════════════════════════════
    // 1. TelephonyManager — IMEI, IMSI, SIM, operator
    // ══════════════════════════════════════════════════

    try {
        var TelephonyManager = Java.use('android.telephony.TelephonyManager');

        // getDeviceId() — IMEI (deprecated but still used)
        try {
            TelephonyManager.getDeviceId.overload().implementation = function() {
                var result = this.getDeviceId();
                log('TelephonyManager', 'getDeviceId()', result);
                return result;
            };
        } catch(e) {}

        try {
            TelephonyManager.getDeviceId.overload('int').implementation = function(slot) {
                var result = this.getDeviceId(slot);
                log('TelephonyManager', 'getDeviceId(int)', result, {slot: slot});
                return result;
            };
        } catch(e) {}

        // getImei()
        try {
            TelephonyManager.getImei.overload().implementation = function() {
                var result = this.getImei();
                log('TelephonyManager', 'getImei()', result);
                return result;
            };
        } catch(e) {}

        try {
            TelephonyManager.getImei.overload('int').implementation = function(slot) {
                var result = this.getImei(slot);
                log('TelephonyManager', 'getImei(int)', result, {slot: slot});
                return result;
            };
        } catch(e) {}

        // getSubscriberId() — IMSI
        try {
            TelephonyManager.getSubscriberId.overload().implementation = function() {
                var result = this.getSubscriberId();
                log('TelephonyManager', 'getSubscriberId()', result);
                return result;
            };
        } catch(e) {}

        // getSimSerialNumber()
        try {
            TelephonyManager.getSimSerialNumber.overload().implementation = function() {
                var result = this.getSimSerialNumber();
                log('TelephonyManager', 'getSimSerialNumber()', result);
                return result;
            };
        } catch(e) {}

        // getLine1Number() — phone number
        try {
            TelephonyManager.getLine1Number.overload().implementation = function() {
                var result = this.getLine1Number();
                log('TelephonyManager', 'getLine1Number()', result);
                return result;
            };
        } catch(e) {}

        // getNetworkOperator()
        try {
            TelephonyManager.getNetworkOperator.overload().implementation = function() {
                var result = this.getNetworkOperator();
                log('TelephonyManager', 'getNetworkOperator()', result);
                return result;
            };
        } catch(e) {}

        // getNetworkOperatorName()
        try {
            TelephonyManager.getNetworkOperatorName.overload().implementation = function() {
                var result = this.getNetworkOperatorName();
                log('TelephonyManager', 'getNetworkOperatorName()', result);
                return result;
            };
        } catch(e) {}

        // getSimOperator()
        try {
            TelephonyManager.getSimOperator.overload().implementation = function() {
                var result = this.getSimOperator();
                log('TelephonyManager', 'getSimOperator()', result);
                return result;
            };
        } catch(e) {}

        console.log('[+] TelephonyManager hooked');
    } catch(e) {
        console.log('[-] TelephonyManager hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 2. Settings.Secure — Android ID, etc.
    // ══════════════════════════════════════════════════

    try {
        var Secure = Java.use('android.provider.Settings$Secure');

        Secure.getString.overload('android.content.ContentResolver', 'java.lang.String').implementation = function(resolver, name) {
            var result = this.getString(resolver, name);
            log('Settings.Secure', 'getString', result, {name: name});
            return result;
        };

        console.log('[+] Settings.Secure hooked');
    } catch(e) {
        console.log('[-] Settings.Secure hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 3. Build — device model, manufacturer, serial
    // ══════════════════════════════════════════════════

    try {
        var Build = Java.use('android.os.Build');

        // Log all static fields on first access
        var buildFields = ['MODEL', 'MANUFACTURER', 'BRAND', 'DEVICE', 'PRODUCT',
                          'HARDWARE', 'BOARD', 'DISPLAY', 'FINGERPRINT', 'HOST',
                          'ID', 'TAGS', 'TYPE', 'USER', 'SERIAL'];
        buildFields.forEach(function(field) {
            try {
                var val = Build[field].value;
                log('Build', field, val);
            } catch(e) {}
        });

        // Build.VERSION fields
        var BuildVersion = Java.use('android.os.Build$VERSION');
        ['SDK_INT', 'RELEASE', 'CODENAME', 'INCREMENTAL', 'SECURITY_PATCH'].forEach(function(field) {
            try {
                var val = BuildVersion[field].value;
                log('Build.VERSION', field, val);
            } catch(e) {}
        });

        // getSerial() — Android 8+
        try {
            Build.getSerial.implementation = function() {
                var result = this.getSerial();
                log('Build', 'getSerial()', result);
                return result;
            };
        } catch(e) {}

        console.log('[+] Build fields logged');
    } catch(e) {
        console.log('[-] Build hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 4. NetworkInterface — MAC address
    // ══════════════════════════════════════════════════

    try {
        var NetworkInterface = Java.use('java.net.NetworkInterface');

        NetworkInterface.getHardwareAddress.implementation = function() {
            var result = this.getHardwareAddress();
            var mac = result ? Array.from(result).map(function(b) {
                return ('0' + ((b & 0xff).toString(16))).slice(-2);
            }).join(':') : null;
            log('NetworkInterface', 'getHardwareAddress()', mac, {iface: this.getName()});
            return result;
        };

        console.log('[+] NetworkInterface hooked');
    } catch(e) {
        console.log('[-] NetworkInterface hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 5. WifiInfo — SSID, BSSID, MAC
    // ══════════════════════════════════════════════════

    try {
        var WifiInfo = Java.use('android.net.wifi.WifiInfo');

        try {
            WifiInfo.getMacAddress.implementation = function() {
                var result = this.getMacAddress();
                log('WifiInfo', 'getMacAddress()', result);
                return result;
            };
        } catch(e) {}

        try {
            WifiInfo.getSSID.implementation = function() {
                var result = this.getSSID();
                log('WifiInfo', 'getSSID()', result);
                return result;
            };
        } catch(e) {}

        try {
            WifiInfo.getBSSID.implementation = function() {
                var result = this.getBSSID();
                log('WifiInfo', 'getBSSID()', result);
                return result;
            };
        } catch(e) {}

        console.log('[+] WifiInfo hooked');
    } catch(e) {
        console.log('[-] WifiInfo hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 6. Google Advertising ID
    // ══════════════════════════════════════════════════

    try {
        var AdvertisingIdClient = Java.use('com.google.android.gms.ads.identifier.AdvertisingIdClient$Info');

        AdvertisingIdClient.getId.implementation = function() {
            var result = this.getId();
            log('AdvertisingIdClient', 'getId()', result);
            return result;
        };

        AdvertisingIdClient.isLimitAdTrackingEnabled.implementation = function() {
            var result = this.isLimitAdTrackingEnabled();
            log('AdvertisingIdClient', 'isLimitAdTrackingEnabled()', result);
            return result;
        };

        console.log('[+] AdvertisingIdClient hooked');
    } catch(e) {
        console.log('[-] AdvertisingIdClient hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 7. LocationManager — GPS coordinates
    // ══════════════════════════════════════════════════

    try {
        var LocationManager = Java.use('android.location.LocationManager');

        try {
            LocationManager.getLastKnownLocation.overload('java.lang.String').implementation = function(provider) {
                var result = this.getLastKnownLocation(provider);
                var coords = result ? {lat: result.getLatitude(), lon: result.getLongitude()} : null;
                log('LocationManager', 'getLastKnownLocation', coords ? JSON.stringify(coords) : null, {provider: provider});
                return result;
            };
        } catch(e) {}

        console.log('[+] LocationManager hooked');
    } catch(e) {
        console.log('[-] LocationManager hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 8. PackageManager — installed apps enumeration
    // ══════════════════════════════════════════════════

    try {
        var PackageManager = Java.use('android.app.ApplicationPackageManager');

        try {
            PackageManager.getInstalledPackages.overload('int').implementation = function(flags) {
                var result = this.getInstalledPackages(flags);
                log('PackageManager', 'getInstalledPackages()', 'count=' + result.size(), {flags: flags});
                return result;
            };
        } catch(e) {}

        try {
            PackageManager.getInstalledApplications.overload('int').implementation = function(flags) {
                var result = this.getInstalledApplications(flags);
                log('PackageManager', 'getInstalledApplications()', 'count=' + result.size(), {flags: flags});
                return result;
            };
        } catch(e) {}

        console.log('[+] PackageManager hooked');
    } catch(e) {
        console.log('[-] PackageManager hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 9. AccountManager — Google accounts
    // ══════════════════════════════════════════════════

    try {
        var AccountManager = Java.use('android.accounts.AccountManager');

        try {
            AccountManager.getAccounts.implementation = function() {
                var result = this.getAccounts();
                log('AccountManager', 'getAccounts()', 'count=' + result.length);
                return result;
            };
        } catch(e) {}

        try {
            AccountManager.getAccountsByType.overload('java.lang.String').implementation = function(type) {
                var result = this.getAccountsByType(type);
                log('AccountManager', 'getAccountsByType()', 'count=' + result.length, {type: type});
                return result;
            };
        } catch(e) {}

        console.log('[+] AccountManager hooked');
    } catch(e) {
        console.log('[-] AccountManager hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 10. SensorManager — device sensors list
    // ══════════════════════════════════════════════════

    try {
        var SensorManager = Java.use('android.hardware.SensorManager');

        SensorManager.getSensorList.overload('int').implementation = function(type) {
            var result = this.getSensorList(type);
            log('SensorManager', 'getSensorList()', 'count=' + result.size(), {type: type});
            return result;
        };

        console.log('[+] SensorManager hooked');
    } catch(e) {
        console.log('[-] SensorManager hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 11. File reads — /proc/cpuinfo, /sys/ etc.
    // ══════════════════════════════════════════════════

    try {
        var FileInputStream = Java.use('java.io.FileInputStream');

        FileInputStream.$init.overload('java.lang.String').implementation = function(path) {
            // Only log interesting paths
            if (path && (path.indexOf('/proc/') === 0 ||
                         path.indexOf('/sys/') === 0 ||
                         path.indexOf('/system/') === 0 ||
                         path.indexOf('build.prop') !== -1)) {
                log('FileInputStream', 'open', path);
            }
            return this.$init(path);
        };

        var File = Java.use('java.io.File');
        FileInputStream.$init.overload('java.io.File').implementation = function(file) {
            var path = file.getAbsolutePath();
            if (path && (path.indexOf('/proc/') === 0 ||
                         path.indexOf('/sys/') === 0 ||
                         path.indexOf('/system/') === 0 ||
                         path.indexOf('build.prop') !== -1)) {
                log('FileInputStream', 'open(File)', path);
            }
            return this.$init(file);
        };

        console.log('[+] FileInputStream hooked');
    } catch(e) {
        console.log('[-] FileInputStream hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 12. Display metrics — screen size, density
    // ══════════════════════════════════════════════════

    try {
        var DisplayMetrics = Java.use('android.util.DisplayMetrics');

        // Log density and screen size when metrics are populated
        var origGetMetrics = null;
        var Display = Java.use('android.view.Display');
        try {
            Display.getMetrics.overload('android.util.DisplayMetrics').implementation = function(metrics) {
                this.getMetrics(metrics);
                log('Display', 'getMetrics()', null, {
                    widthPixels: metrics.widthPixels.value,
                    heightPixels: metrics.heightPixels.value,
                    density: metrics.density.value,
                    densityDpi: metrics.densityDpi.value,
                });
            };
        } catch(e) {}

        console.log('[+] Display hooked');
    } catch(e) {
        console.log('[-] Display hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 13. System.getProperty — os.arch, java.vm, etc.
    // ══════════════════════════════════════════════════

    try {
        var System = Java.use('java.lang.System');

        System.getProperty.overload('java.lang.String').implementation = function(key) {
            var result = this.getProperty(key);
            // Only log device-related properties
            if (key && (key.indexOf('os.') === 0 ||
                        key.indexOf('java.vm') === 0 ||
                        key.indexOf('ro.') === 0 ||
                        key === 'http.agent')) {
                log('System', 'getProperty', result, {key: key});
            }
            return result;
        };

        console.log('[+] System.getProperty hooked');
    } catch(e) {
        console.log('[-] System.getProperty hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 14. ContentResolver.query — potentially used for
    //     telephony, contacts, or other providers
    // ══════════════════════════════════════════════════

    try {
        var ContentResolver = Java.use('android.content.ContentResolver');

        ContentResolver.query.overload(
            'android.net.Uri', '[Ljava.lang.String;', 'java.lang.String',
            '[Ljava.lang.String;', 'java.lang.String'
        ).implementation = function(uri, projection, selection, selectionArgs, sortOrder) {
            var uriStr = uri.toString();
            // Log telephony and SIM-related queries
            if (uriStr.indexOf('telephony') !== -1 ||
                uriStr.indexOf('siminfo') !== -1 ||
                uriStr.indexOf('settings') !== -1) {
                log('ContentResolver', 'query', uriStr);
            }
            return this.query(uri, projection, selection, selectionArgs, sortOrder);
        };

        console.log('[+] ContentResolver hooked');
    } catch(e) {
        console.log('[-] ContentResolver hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 15. Runtime.exec — shell commands for device info
    // ══════════════════════════════════════════════════

    try {
        var Runtime = Java.use('java.lang.Runtime');

        Runtime.exec.overload('java.lang.String').implementation = function(cmd) {
            log('Runtime', 'exec(String)', cmd);
            return this.exec(cmd);
        };

        Runtime.exec.overload('[Ljava.lang.String;').implementation = function(cmdArray) {
            var cmd = cmdArray ? Array.from(cmdArray).join(' ') : null;
            log('Runtime', 'exec(String[])', cmd);
            return this.exec(cmdArray);
        };

        console.log('[+] Runtime.exec hooked');
    } catch(e) {
        console.log('[-] Runtime.exec hook failed: ' + e);
    }


    // ══════════════════════════════════════════════════
    // 16. WebView User-Agent
    // ══════════════════════════════════════════════════

    try {
        var WebSettings = Java.use('android.webkit.WebSettings');

        try {
            WebSettings.setUserAgentString.overload('java.lang.String').implementation = function(ua) {
                log('WebSettings', 'setUserAgentString', ua);
                return this.setUserAgentString(ua);
            };
        } catch(e) {}

        try {
            WebSettings.getUserAgentString.implementation = function() {
                var result = this.getUserAgentString();
                log('WebSettings', 'getUserAgentString', result);
                return result;
            };
        } catch(e) {}

        console.log('[+] WebSettings hooked');
    } catch(e) {
        console.log('[-] WebSettings hook failed: ' + e);
    }


    console.log('[*] All hooks installed. Launch Avito and wait 30-60 seconds.');
    console.log('[*] Then close Avito and analyze SNIFF| lines in output.');
});
