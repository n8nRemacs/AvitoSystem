// Frida script to hook fingerprint generation in Avito
Java.perform(function() {
    console.log("[*] Hooking fingerprint generation...");

    // Hook System.loadLibrary to see what libraries are loaded
    var System = Java.use("java.lang.System");
    System.loadLibrary.overload('java.lang.String').implementation = function(libname) {
        console.log("[loadLibrary] " + libname);
        return this.loadLibrary(libname);
    };

    // Try to hook FingerprintService
    try {
        var FingerprintService = Java.use("com.avito.security.libfp.FingerprintService");
        console.log("[+] Found FingerprintService class");

        // Hook all methods
        FingerprintService.class.getDeclaredMethods().forEach(function(method) {
            console.log("  Method: " + method.getName());
        });
    } catch(e) {
        console.log("[-] FingerprintService not found: " + e);
    }

    // Try to hook Application class from libfp package
    try {
        var LibfpApp = Java.use("com.avito.security.libfp.Application");
        console.log("[+] Found libfp.Application class");

        LibfpApp.class.getDeclaredMethods().forEach(function(method) {
            console.log("  Method: " + method.getName());
        });
    } catch(e) {
        console.log("[-] libfp.Application not found: " + e);
    }

    // Hook SharedPreferences to see fpx being written
    var SharedPreferencesEditor = Java.use("android.app.SharedPreferencesImpl$EditorImpl");
    SharedPreferencesEditor.putString.implementation = function(key, value) {
        if (key.indexOf("fp") !== -1) {
            console.log("[SharedPrefs] " + key + " = " + value.substring(0, 100) + "...");
        }
        return this.putString(key, value);
    };

    // Hook String class to catch fingerprint generation
    var String = Java.use("java.lang.String");
    String.valueOf.overload('java.lang.Object').implementation = function(obj) {
        var result = this.valueOf(obj);
        if (result && result.toString().startsWith("A2.")) {
            console.log("[!] Fingerprint generated: " + result.substring(0, 50) + "...");
            console.log(Java.use("android.util.Log").getStackTraceString(Java.use("java.lang.Exception").$new()));
        }
        return result;
    };

    console.log("[*] Hooks installed");
});
