/**
 * Build Properties Masking Script
 *
 * This script hooks Android Build class and replaces device properties
 * to make emulator appear as Google Pixel 6
 *
 * Usage:
 *   frida -U -f com.avito.android -l build_mask.js --no-pause
 */

Java.perform(function() {
    console.log('[*] Build Properties Masking script loaded');

    try {
        var Build = Java.use('android.os.Build');

        // Hook MODEL
        Build.MODEL.value = 'Pixel 6';
        console.log('[+] Build.MODEL -> Pixel 6');

        // Hook MANUFACTURER
        Build.MANUFACTURER.value = 'Google';
        console.log('[+] Build.MANUFACTURER -> Google');

        // Hook BRAND
        Build.BRAND.value = 'google';
        console.log('[+] Build.BRAND -> google');

        // Hook PRODUCT
        Build.PRODUCT.value = 'oriole';
        console.log('[+] Build.PRODUCT -> oriole');

        // Hook DEVICE
        Build.DEVICE.value = 'oriole';
        console.log('[+] Build.DEVICE -> oriole');

        // Hook FINGERPRINT
        Build.FINGERPRINT.value = 'google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys';
        console.log('[+] Build.FINGERPRINT -> google/oriole/...');

        // Hook HARDWARE
        Build.HARDWARE.value = 'oriole';
        console.log('[+] Build.HARDWARE -> oriole');

        // Hook TAGS (remove emulator indicators)
        Build.TAGS.value = 'release-keys';
        console.log('[+] Build.TAGS -> release-keys');

        console.log('[*] ========================================');
        console.log('[*] Device now appears as: Google Pixel 6');
        console.log('[*] ========================================');

    } catch (e) {
        console.log('[-] Error hooking Build class: ' + e);
    }

    // Hook SystemProperties for additional masking
    try {
        var SystemProperties = Java.use('android.os.SystemProperties');

        SystemProperties.get.overload('java.lang.String').implementation = function(key) {
            var value = this.get(key);

            // Mask emulator-related properties
            if (key === 'ro.product.model') {
                value = 'Pixel 6';
                console.log('[SystemProperties] ' + key + ' -> Pixel 6');
            } else if (key === 'ro.product.manufacturer') {
                value = 'Google';
                console.log('[SystemProperties] ' + key + ' -> Google');
            } else if (key === 'ro.product.brand') {
                value = 'google';
            } else if (key === 'ro.product.device') {
                value = 'oriole';
            } else if (key === 'ro.product.name') {
                value = 'oriole';
            } else if (key === 'ro.build.fingerprint') {
                value = 'google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys';
            } else if (key.includes('emulator') || key.includes('qemu')) {
                value = '';  // Hide emulator indicators
            }

            return value;
        };

        SystemProperties.get.overload('java.lang.String', 'java.lang.String').implementation = function(key, def) {
            var value = this.get(key, def);

            // Same masking logic
            if (key === 'ro.product.model') {
                value = 'Pixel 6';
            } else if (key === 'ro.product.manufacturer') {
                value = 'Google';
            } else if (key === 'ro.product.brand') {
                value = 'google';
            } else if (key === 'ro.product.device') {
                value = 'oriole';
            } else if (key === 'ro.product.name') {
                value = 'oriole';
            } else if (key === 'ro.build.fingerprint') {
                value = 'google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys';
            } else if (key.includes('emulator') || key.includes('qemu')) {
                value = '';
            }

            return value;
        };

        console.log('[+] SystemProperties hooked');

    } catch (e) {
        console.log('[-] Could not hook SystemProperties: ' + e);
    }

    // Hook Settings.Secure to hide emulator indicators
    try {
        var SettingsSecure = Java.use('android.provider.Settings$Secure');

        SettingsSecure.getString.overload('android.content.ContentResolver', 'java.lang.String').implementation = function(resolver, name) {
            var value = this.getString(resolver, name);

            // Hide android_id that might indicate emulator
            if (name === 'android_id' && value === '0000000000000000') {
                value = Math.random().toString(36).substring(2, 18);
                console.log('[SettingsSecure] Generated android_id: ' + value);
            }

            return value;
        };

        console.log('[+] Settings.Secure hooked');

    } catch (e) {
        console.log('[-] Could not hook Settings.Secure: ' + e);
    }

    console.log('[*] Build masking complete!');
});
