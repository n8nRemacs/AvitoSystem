// Quick runtime fingerprint sniff - hooks all major fingerprint APIs
// Designed to capture as much as possible in a few seconds

var results = {};

function log(category, method, value) {
    if (!results[category]) results[category] = {};
    results[category][method] = value;
    send(JSON.stringify({cat: category, method: method, value: String(value).substring(0, 200)}));
}

Java.perform(function() {
    send("[*] Java.perform started - hooking APIs...");

    // === Settings.Secure (ANDROID_ID) ===
    try {
        var Secure = Java.use("android.provider.Settings$Secure");
        Secure.getString.overload("android.content.ContentResolver", "java.lang.String").implementation = function(cr, name) {
            var val = this.getString(cr, name);
            log("Settings.Secure", name, val);
            return val;
        };
    } catch(e) { send("[!] Settings.Secure hook failed: " + e); }

    // === TelephonyManager ===
    try {
        var TM = Java.use("android.telephony.TelephonyManager");
        ["getDeviceId", "getImei", "getSubscriberId", "getLine1Number", "getSimSerialNumber",
         "getNetworkOperator", "getNetworkOperatorName", "getSimOperator", "getSimOperatorName",
         "getNetworkCountryIso", "getSimCountryIso", "getPhoneType", "getNetworkType"].forEach(function(m) {
            try {
                TM[m].overloads.forEach(function(overload) {
                    overload.implementation = function() {
                        var val = overload.apply(this, arguments);
                        log("TelephonyManager", m, val);
                        return val;
                    };
                });
            } catch(e) {}
        });
    } catch(e) { send("[!] TelephonyManager hook failed: " + e); }

    // === Build fields (read statically) ===
    try {
        var Build = Java.use("android.os.Build");
        ["MODEL", "MANUFACTURER", "BRAND", "DEVICE", "PRODUCT", "FINGERPRINT",
         "HARDWARE", "BOARD", "DISPLAY", "HOST", "ID", "TYPE", "TAGS"].forEach(function(f) {
            try {
                log("Build", f, Build[f].value);
            } catch(e) {}
        });
        var Version = Java.use("android.os.Build$VERSION");
        ["SDK_INT", "RELEASE", "CODENAME", "INCREMENTAL", "SECURITY_PATCH"].forEach(function(f) {
            try {
                log("Build.VERSION", f, Version[f].value);
            } catch(e) {}
        });
    } catch(e) { send("[!] Build hook failed: " + e); }

    // === WifiManager / WifiInfo ===
    try {
        var WifiInfo = Java.use("android.net.wifi.WifiInfo");
        ["getMacAddress", "getSSID", "getBSSID", "getIpAddress", "getLinkSpeed", "getFrequency"].forEach(function(m) {
            try {
                WifiInfo[m].overloads.forEach(function(overload) {
                    overload.implementation = function() {
                        var val = overload.apply(this, arguments);
                        log("WifiInfo", m, val);
                        return val;
                    };
                });
            } catch(e) {}
        });
    } catch(e) { send("[!] WifiInfo hook failed: " + e); }

    // === DisplayMetrics ===
    try {
        var DM = Java.use("android.util.DisplayMetrics");
        DM.toString.implementation = function() {
            var s = this.toString();
            log("DisplayMetrics", "density", this.density.value);
            log("DisplayMetrics", "densityDpi", this.densityDpi.value);
            log("DisplayMetrics", "widthPixels", this.widthPixels.value);
            log("DisplayMetrics", "heightPixels", this.heightPixels.value);
            log("DisplayMetrics", "xdpi", this.xdpi.value);
            log("DisplayMetrics", "ydpi", this.ydpi.value);
            return s;
        };
    } catch(e) {}

    // === ContentResolver query (for content providers) ===
    try {
        var CR = Java.use("android.content.ContentResolver");
        CR.query.overload("android.net.Uri", "[Ljava.lang.String;", "java.lang.String", "[Ljava.lang.String;", "java.lang.String").implementation = function(uri, proj, sel, args, order) {
            log("ContentResolver", "query", uri.toString());
            return this.query(uri, proj, sel, args, order);
        };
    } catch(e) {}

    // === PackageManager.getInstalledPackages ===
    try {
        var PM = Java.use("android.app.ApplicationPackageManager");
        PM.getInstalledPackages.overloads.forEach(function(overload) {
            overload.implementation = function() {
                var val = overload.apply(this, arguments);
                log("PackageManager", "getInstalledPackages", "count=" + val.size());
                return val;
            };
        });
        PM.getInstalledApplications.overloads.forEach(function(overload) {
            overload.implementation = function() {
                var val = overload.apply(this, arguments);
                log("PackageManager", "getInstalledApplications", "count=" + val.size());
                return val;
            };
        });
    } catch(e) {}

    // === SensorManager ===
    try {
        var SM = Java.use("android.hardware.SensorManager");
        SM.getSensorList.implementation = function(type) {
            var val = this.getSensorList(type);
            log("SensorManager", "getSensorList(type=" + type + ")", "count=" + val.size());
            return val;
        };
    } catch(e) {}

    // === Advertising ID ===
    try {
        var AIC = Java.use("com.google.android.gms.ads.identifier.AdvertisingIdClient$Info");
        AIC.getId.implementation = function() {
            var val = this.getId();
            log("AdvertisingId", "GAID", val);
            return val;
        };
        AIC.isLimitAdTrackingEnabled.implementation = function() {
            var val = this.isLimitAdTrackingEnabled();
            log("AdvertisingId", "limitAdTracking", val);
            return val;
        };
    } catch(e) {}

    // === System.getProperty / SystemProperties ===
    try {
        var System = Java.use("java.lang.System");
        System.getProperty.overload("java.lang.String").implementation = function(key) {
            var val = this.getProperty(key);
            if (val !== null) log("System.getProperty", key, val);
            return val;
        };
    } catch(e) {}

    // === Runtime.exec (shell commands) ===
    try {
        var Runtime = Java.use("java.lang.Runtime");
        Runtime.exec.overload("java.lang.String").implementation = function(cmd) {
            log("Runtime.exec", "command", cmd);
            return this.exec(cmd);
        };
        Runtime.exec.overload("[Ljava.lang.String;").implementation = function(cmds) {
            log("Runtime.exec", "command[]", Java.array("java.lang.String", cmds).join(" "));
            return this.exec(cmds);
        };
    } catch(e) {}

    // === File access (key paths) ===
    try {
        var File = Java.use("java.io.File");
        File.exists.implementation = function() {
            var path = this.getAbsolutePath();
            var val = this.exists();
            if (path.indexOf("/proc/") !== -1 || path.indexOf("/sys/") !== -1 ||
                path.indexOf("/su") !== -1 || path.indexOf("Superuser") !== -1 ||
                path.indexOf("Magisk") !== -1 || path.indexOf("frida") !== -1 ||
                path.indexOf("xposed") !== -1 || path.indexOf("/sbin/") !== -1) {
                log("File.exists", path, val);
            }
            return val;
        };
    } catch(e) {}

    // === WebView User-Agent ===
    try {
        var WS = Java.use("android.webkit.WebSettings");
        WS.getUserAgentString.implementation = function() {
            var val = this.getUserAgentString();
            log("WebView", "userAgent", val);
            return val;
        };
        WS.setUserAgentString.implementation = function(ua) {
            log("WebView", "setUserAgent", ua);
            return this.setUserAgentString(ua);
        };
    } catch(e) {}

    // === Location ===
    try {
        var LM = Java.use("android.location.LocationManager");
        LM.getLastKnownLocation.overloads.forEach(function(overload) {
            overload.implementation = function() {
                var val = overload.apply(this, arguments);
                log("Location", "getLastKnownLocation(" + arguments[0] + ")", val ? val.toString() : "null");
                return val;
            };
        });
    } catch(e) {}

    // === AccountManager ===
    try {
        var AM = Java.use("android.accounts.AccountManager");
        AM.getAccounts.implementation = function() {
            var val = this.getAccounts();
            log("AccountManager", "getAccounts", "count=" + val.length);
            return val;
        };
        AM.getAccountsByType.implementation = function(type) {
            var val = this.getAccountsByType(type);
            log("AccountManager", "getAccountsByType(" + type + ")", "count=" + val.length);
            return val;
        };
    } catch(e) {}

    // === OkHttp interceptor for headers ===
    try {
        var Interceptor = Java.use("okhttp3.Interceptor$Chain");
        // Try to hook Request.header() to see what headers are set
        var Request = Java.use("okhttp3.Request");
        Request.header.implementation = function(name) {
            var val = this.header(name);
            if (name && (name.toLowerCase().indexOf("device") !== -1 ||
                         name.toLowerCase().indexOf("fingerprint") !== -1 ||
                         name.toLowerCase().indexOf("x-") === 0)) {
                log("HTTP.Header", name, val);
            }
            return val;
        };
    } catch(e) {}

    // Dump Build info immediately
    send("[*] Hooks installed. Dumping static Build info...");

    // After 5 seconds, dump all results
    setTimeout(function() {
        send("[RESULTS] " + JSON.stringify(results));
    }, 5000);

    // After 30 seconds, dump again
    setTimeout(function() {
        send("[RESULTS_30S] " + JSON.stringify(results));
    }, 30000);
});
