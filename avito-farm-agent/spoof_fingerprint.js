/**
 * spoof_fingerprint.js — Frida script to spoof device identity per Android profile.
 *
 * Each Android user profile needs a unique device fingerprint so Avito sees them
 * as separate physical devices. This script hooks system APIs and returns
 * per-profile spoofed values.
 *
 * Usage:
 *   frida -U -f com.avito.android -l spoof_fingerprint.js --no-pause
 *
 * Configuration: set PROFILE_ID environment variable or pass via Frida --parameters
 * The profile config is loaded from /data/local/tmp/farm_profiles/{profile_id}.json
 *
 * NOTE: Update this script after running sniff_fingerprint.js to only hook
 * the APIs that Avito actually uses. See DOCS/AVITO-FINGERPRINT.md.
 */

'use strict';

// ── Profile config loading ───────────────────────────

var PROFILE_CONFIG = null;
var PROFILES_DIR = '/data/local/tmp/farm_profiles/';

function loadProfileConfig() {
    /**
     * Profile config JSON format:
     * {
     *   "profile_id": 10,
     *   "android_id": "a1b2c3d4e5f6g7h8",
     *   "imei": "351234567890123",
     *   "imsi": "250021234567890",
     *   "serial": "ABCDEF123456",
     *   "mac": "02:00:00:12:34:56",
     *   "gaid": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
     *   "model": "OnePlus LE2115",
     *   "manufacturer": "OnePlus",
     *   "brand": "OnePlus",
     *   "device": "OnePlus8T",
     *   "product": "OnePlus8T",
     *   "fingerprint": "OnePlus/OnePlus8T/OnePlus8T:14/UQ1A.240205.002/1234567:user/release-keys",
     *   "build_id": "UQ1A.240205.002",
     *   "sim_operator": "25002",
     *   "sim_operator_name": "MegaFon",
     *   "network_operator": "25002",
     *   "phone_number": "+79001234567"
     * }
     */
    try {
        var profileId = Java.use('android.os.UserHandle').myUserId();
        var configPath = PROFILES_DIR + profileId + '.json';

        var File = Java.use('java.io.File');
        var configFile = File.$new(configPath);

        if (!configFile.exists()) {
            console.log('[!] No profile config at ' + configPath + ', using defaults');
            return null;
        }

        var fis = Java.use('java.io.FileInputStream').$new(configFile);
        var length = configFile.length();
        var bytes = Java.array('byte', new Array(length).fill(0));
        fis.read(bytes);
        fis.close();

        var content = Java.use('java.lang.String').$new(bytes).toString();
        return JSON.parse(content);
    } catch(e) {
        console.log('[-] Failed to load profile config: ' + e);
        return null;
    }
}


// ── Spoof hooks ──────────────────────────────────────

Java.perform(function() {
    PROFILE_CONFIG = loadProfileConfig();

    if (!PROFILE_CONFIG) {
        console.log('[!] spoof_fingerprint.js: no config, hooks inactive');
        return;
    }

    var cfg = PROFILE_CONFIG;
    console.log('[*] Spoofing profile ' + cfg.profile_id + ' as ' + (cfg.model || 'unknown'));


    // ── 1. Settings.Secure (Android ID) ──────────────

    if (cfg.android_id) {
        try {
            var Secure = Java.use('android.provider.Settings$Secure');
            var originalGetString = Secure.getString;

            Secure.getString.overload('android.content.ContentResolver', 'java.lang.String').implementation = function(resolver, name) {
                if (name === 'android_id') {
                    return cfg.android_id;
                }
                return originalGetString.call(this, resolver, name);
            };
            console.log('[+] Spoofed: android_id → ' + cfg.android_id);
        } catch(e) {}
    }


    // ── 2. TelephonyManager ──────────────────────────

    try {
        var TM = Java.use('android.telephony.TelephonyManager');

        if (cfg.imei) {
            try {
                TM.getDeviceId.overload().implementation = function() { return cfg.imei; };
                TM.getDeviceId.overload('int').implementation = function(s) { return cfg.imei; };
            } catch(e) {}
            try {
                TM.getImei.overload().implementation = function() { return cfg.imei; };
                TM.getImei.overload('int').implementation = function(s) { return cfg.imei; };
            } catch(e) {}
            console.log('[+] Spoofed: IMEI → ' + cfg.imei);
        }

        if (cfg.imsi) {
            try {
                TM.getSubscriberId.overload().implementation = function() { return cfg.imsi; };
            } catch(e) {}
        }

        if (cfg.phone_number) {
            try {
                TM.getLine1Number.overload().implementation = function() { return cfg.phone_number; };
            } catch(e) {}
        }

        if (cfg.sim_operator) {
            try {
                TM.getSimOperator.overload().implementation = function() { return cfg.sim_operator; };
            } catch(e) {}
            try {
                TM.getNetworkOperator.overload().implementation = function() { return cfg.network_operator || cfg.sim_operator; };
            } catch(e) {}
        }

        if (cfg.sim_operator_name) {
            try {
                TM.getSimOperatorName.overload().implementation = function() { return cfg.sim_operator_name; };
            } catch(e) {}
            try {
                TM.getNetworkOperatorName.overload().implementation = function() { return cfg.sim_operator_name; };
            } catch(e) {}
        }
    } catch(e) {
        console.log('[-] TelephonyManager spoof failed: ' + e);
    }


    // ── 3. Build fields ──────────────────────────────

    try {
        var Build = Java.use('android.os.Build');

        var fieldMap = {
            'MODEL': cfg.model,
            'MANUFACTURER': cfg.manufacturer,
            'BRAND': cfg.brand,
            'DEVICE': cfg.device,
            'PRODUCT': cfg.product,
            'FINGERPRINT': cfg.fingerprint,
            'SERIAL': cfg.serial,
            'HARDWARE': cfg.hardware,
            'BOARD': cfg.board,
            'DISPLAY': cfg.display,
            'ID': cfg.build_id,
        };

        for (var field in fieldMap) {
            if (fieldMap[field]) {
                try {
                    Build[field].value = fieldMap[field];
                } catch(e) {}
            }
        }

        if (cfg.serial) {
            try {
                Build.getSerial.implementation = function() { return cfg.serial; };
            } catch(e) {}
        }

        console.log('[+] Spoofed: Build fields (model=' + cfg.model + ')');
    } catch(e) {
        console.log('[-] Build spoof failed: ' + e);
    }


    // ── 4. Network (MAC address) ─────────────────────

    if (cfg.mac) {
        try {
            var NetworkInterface = Java.use('java.net.NetworkInterface');
            NetworkInterface.getHardwareAddress.implementation = function() {
                var parts = cfg.mac.split(':');
                var bytes = Java.array('byte', parts.map(function(h) {
                    return parseInt(h, 16);
                }));
                return bytes;
            };
            console.log('[+] Spoofed: MAC → ' + cfg.mac);
        } catch(e) {}

        try {
            var WifiInfo = Java.use('android.net.wifi.WifiInfo');
            WifiInfo.getMacAddress.implementation = function() { return cfg.mac; };
        } catch(e) {}
    }


    // ── 5. Google Advertising ID ─────────────────────

    if (cfg.gaid) {
        try {
            var AdInfo = Java.use('com.google.android.gms.ads.identifier.AdvertisingIdClient$Info');
            AdInfo.getId.implementation = function() { return cfg.gaid; };
            console.log('[+] Spoofed: GAID → ' + cfg.gaid);
        } catch(e) {}
    }


    // ── 6. Display metrics ───────────────────────────

    if (cfg.screen_width && cfg.screen_height) {
        try {
            var Display = Java.use('android.view.Display');
            Display.getMetrics.overload('android.util.DisplayMetrics').implementation = function(metrics) {
                this.getMetrics(metrics);
                metrics.widthPixels.value = cfg.screen_width;
                metrics.heightPixels.value = cfg.screen_height;
                if (cfg.density) metrics.density.value = cfg.density;
                if (cfg.density_dpi) metrics.densityDpi.value = cfg.density_dpi;
            };
        } catch(e) {}
    }


    console.log('[*] Fingerprint spoofing active for profile ' + cfg.profile_id);
});
