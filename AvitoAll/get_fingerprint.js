/*
 * Extract fingerprint value from FingerprintStorage
 */

Java.perform(function() {
    console.log("[*] Fingerprint Extractor loaded");

    // Hook FingerprintStorage.a() to get fingerprint value
    try {
        var PrefFingerprintStorage = Java.use('f90.q');

        PrefFingerprintStorage.a.implementation = function() {
            var result = this.a();
            console.log("\n[FINGERPRINT] fpx value: " + result);
            return result;
        };

        PrefFingerprintStorage.b.implementation = function() {
            var result = this.b();
            console.log("[FINGERPRINT] fpx_token value: " + result);
            return result;
        };

        console.log("[+] PrefFingerprintStorage hooked");
    } catch(e) {
        console.log("[-] PrefFingerprintStorage error: " + e);
    }

    // Hook FingerprintService native methods
    try {
        var FingerprintService = Java.use('com.avito.security.libfp.FingerprintService');

        FingerprintService.calculateFingerprintV2.implementation = function(timestamp) {
            console.log("\n[NATIVE] calculateFingerprintV2 called with timestamp: " + timestamp);
            var result = this.calculateFingerprintV2(timestamp);
            console.log("[NATIVE] Result: " + result);
            return result;
        };

        FingerprintService.getToken.implementation = function(fingerprint) {
            console.log("\n[NATIVE] getToken called with: " + fingerprint);
            var result = this.getToken(fingerprint);
            console.log("[NATIVE] Token result: " + result);
            return result;
        };

        console.log("[+] FingerprintService hooked");
    } catch(e) {
        console.log("[-] FingerprintService error: " + e);
    }

    // Hook the header provider to see the value being used
    try {
        var FingerprintHeaderProvider = Java.use('com.avito.android.remote.interceptor.N');

        FingerprintHeaderProvider.getF253512a.implementation = function() {
            var result = this.getF253512a();
            console.log("\n[HEADER PROVIDER] f header value: " + result);
            return result;
        };

        console.log("[+] FingerprintHeaderProvider hooked");
    } catch(e) {
        console.log("[-] FingerprintHeaderProvider error: " + e);
    }

    // Also enumerate all instances of the storage
    setTimeout(function() {
        console.log("\n[*] Enumerating FingerprintStorage instances...");
        try {
            Java.choose('f90.q', {
                onMatch: function(instance) {
                    console.log("[INSTANCE] Found PrefFingerprintStorage");
                    console.log("  fpx: " + instance.a());
                    console.log("  fpx_token: " + instance.b());
                },
                onComplete: function() {
                    console.log("[INSTANCE] Enumeration complete");
                }
            });
        } catch(e) {
            console.log("[-] Enumeration error: " + e);
        }
    }, 3000);

    console.log("\n[*] Fingerprint Extractor READY!");
});
