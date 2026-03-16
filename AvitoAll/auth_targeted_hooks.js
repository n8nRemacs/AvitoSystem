// Targeted Auth Flow Hooks - focuses on key auth classes
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Targeted Auth Flow Capture\n");

        // ============ LoginResult - captures all login outcomes ============
        try {
            var LoginResultOk = Java.use("com.avito.android.remote.model.LoginResult$Ok");
            LoginResultOk["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[LOGIN SUCCESS]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] LoginResult.Ok hooked");
        } catch(e) { console.log("[-] LoginResult.Ok: " + e); }

        // ============ AuthResult - general auth result ============
        try {
            var AuthResult = Java.use("com.avito.android.remote.model.AuthResult");
            AuthResult["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[AUTH RESULT]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] AuthResult hooked");
        } catch(e) {}

        // ============ VerifyCodeResult - SMS code verification ============
        try {
            var VerifyCodeResult = Java.use("com.avito.android.remote.model.registration.VerifyCodeResult$IncorrectData");
            VerifyCodeResult["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[SMS CODE INCORRECT]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        // ============ Phone model ============
        try {
            var Phone = Java.use("com.avito.android.remote.model.user_profile.Phone");
            Phone["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PHONE MODEL]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        // ============ PhonePretendResult - phone validation ============
        try {
            var PhonePretendOk = Java.use("com.avito.android.remote.model.PhonePretendResult$Ok");
            PhonePretendOk["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PHONE PRETEND OK] - Phone number accepted");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] PhonePretendResult hooked");
        } catch(e) {}

        // ============ ConsultationPhoneConfirmationResult ============
        try {
            var PhoneConfirmOk = Java.use("com.avito.android.remote.model.ConsultationPhoneConfirmationResult$Ok");
            PhoneConfirmOk["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PHONE CONFIRMED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        // ============ TFA Check ============
        try {
            var TfaCheck = Java.use("com.avito.android.remote.model.LoginResult$TfaCheckWithPush");
            TfaCheck["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[TFA REQUIRED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] TFA hooked");
        } catch(e) {}

        // ============ WebSocket for auth-related messages ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 || text.indexOf("session") !== -1 ||
                    text.indexOf("phone") !== -1 || text.indexOf("code") !== -1 ||
                    text.indexOf("verify") !== -1 || text.indexOf("login") !== -1) {
                    console.log("\n[WS SEND AUTH] " + text);
                }
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                if (text.indexOf("auth") !== -1 || text.indexOf("session") !== -1 ||
                    text.indexOf("error") !== -1 || text.indexOf("phone") !== -1 ||
                    text.indexOf("code") !== -1 || text.indexOf("verify") !== -1) {
                    console.log("\n[WS RECV AUTH] " + text);
                }
                return this.onReadMessage(text);
            };
            console.log("[+] WebSocket auth filter hooked");
        } catch(e) {}

        // ============ VK ID Auth ============
        try {
            var VKIDAuthParams = Java.use("com.vk.id.auth.VKIDAuthParams");
            VKIDAuthParams["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[VK ID AUTH PARAMS]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        // ============ Session storage ============
        try {
            // Try to find SharedPreferences usage for session
            var SharedPreferences = Java.use("android.content.SharedPreferences");
            var Editor = Java.use("android.content.SharedPreferences$Editor");

            Editor.putString.implementation = function(key, value) {
                if (key && (key.indexOf("session") !== -1 || key.indexOf("token") !== -1 ||
                    key.indexOf("auth") !== -1 || key.indexOf("user") !== -1 ||
                    key.indexOf("refresh") !== -1 || key.indexOf("sessid") !== -1)) {
                    console.log("\n[PREFS WRITE] " + key + " = " + (value ? value.substring(0, 100) : "null"));
                }
                return this.putString(key, value);
            };
            console.log("[+] SharedPreferences hooked");
        } catch(e) {}

        // ============ SSL Bypass ============
        try {
            var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.verifyChain.implementation = function() {
                return arguments[0];
            };
            console.log("[+] SSL bypass active");
        } catch(e) {}

        console.log("\n[*] Ready! Try to login or test auth flow...\n");
    });
}, 1000);
