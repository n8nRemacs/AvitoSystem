// Captcha and HTTP Auth Flow Hooks
setTimeout(function() {
    Java.perform(function() {
        console.log("\n[*] Captcha & HTTP Auth Flow Capture\n");

        // ============ Avito Captcha Interceptors ============
        var captchaClasses = [
            "com.avito.android.captcha.interceptor.a",
            "com.avito.android.captcha.interceptor.b",
            "com.avito.android.captcha.interceptor.e",
            "com.avito.android.captcha.interceptor.g",
            "com.avito.android.captcha.interceptor.i"
        ];

        captchaClasses.forEach(function(className) {
            try {
                var cls = Java.use(className);
                cls.intercept.implementation = function(chain) {
                    var request = chain.request();
                    console.log("\n[CAPTCHA INTERCEPT] " + className);
                    console.log("  URL: " + request.url().toString());
                    console.log("  Method: " + request.method());
                    var response = this.intercept(chain);
                    console.log("  Response: " + response.code());
                    return response;
                };
                console.log("[+] Hooked " + className);
            } catch(e) {}
        });

        // ============ VK Captcha Interceptors ============
        try {
            var VkCaptcha = Java.use("com.vk.id.captcha.okhttp.api.CaptchaHandlingInterceptor");
            VkCaptcha.intercept.implementation = function(chain) {
                var request = chain.request();
                console.log("\n[VK CAPTCHA INTERCEPT]");
                console.log("  URL: " + request.url().toString());
                var response = this.intercept(chain);
                console.log("  Response: " + response.code());
                return response;
            };
            console.log("[+] VK CaptchaHandlingInterceptor hooked");
        } catch(e) {}

        try {
            var HitmanChallenge = Java.use("com.vk.id.captcha.okhttp.api.HitmanChallengeHandlingInterceptor");
            HitmanChallenge.intercept.implementation = function(chain) {
                var request = chain.request();
                console.log("\n[HITMAN CHALLENGE]");
                console.log("  URL: " + request.url().toString());
                var response = this.intercept(chain);
                console.log("  Response: " + response.code());
                return response;
            };
            console.log("[+] HitmanChallengeInterceptor hooked");
        } catch(e) {}

        // ============ Login Failures ============
        try {
            var LoginFailed = Java.use("com.avito.android.remote.model.LoginResult$FailedWithMessage");
            LoginFailed["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[LOGIN FAILED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] LoginResult.FailedWithMessage hooked");
        } catch(e) {}

        try {
            var PassportBlocked = Java.use("com.avito.android.remote.model.LoginResult$PassportBlocked");
            PassportBlocked["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PASSPORT BLOCKED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] PassportBlocked hooked");
        } catch(e) {}

        // ============ Phone Pretend (phone validation) ============
        try {
            var PhoneIncorrect = Java.use("com.avito.android.remote.model.PhonePretendResult$IncorrectData");
            PhoneIncorrect["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PHONE INCORRECT]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        try {
            var PhoneReverify = Java.use("com.avito.android.remote.model.PhonePretendResult$AllowReverification");
            PhoneReverify["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[PHONE REVERIFICATION REQUIRED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch(e) {}

        // ============ Captcha Deeplink ============
        try {
            var CaptchaDeeplink = Java.use("com.avito.android.remote.captcha.model.CaptchaDeeplink");
            CaptchaDeeplink["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[CAPTCHA DEEPLINK]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] CaptchaDeeplink hooked");
        } catch(e) {}

        // ============ API Error Unauthorized ============
        try {
            var Unauthorized = Java.use("com.avito.android.remote.error.ApiError$Unauthorized");
            Unauthorized["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[API UNAUTHORIZED]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] ApiError.Unauthorized hooked");
        } catch(e) {}

        // ============ Social Auth Results ============
        var socialResults = [
            "com.avito.android.remote.model.SocialAuthResult$FollowDeeplink",
            "com.avito.android.remote.model.SocialAuthResult$NeedPhoneVerification",
            "com.avito.android.remote.model.SocialAuthResult$WrongSocialUser",
            "com.avito.android.remote.model.SocialAuthResult$BlockedAccount",
            "com.avito.android.remote.model.SocialAuthResult$FailedWithDialog"
        ];

        socialResults.forEach(function(className) {
            try {
                var cls = Java.use(className);
                cls["$init"].overloads.forEach(function(overload) {
                    overload.implementation = function() {
                        console.log("\n[SOCIAL AUTH] " + className.split("$")[1]);
                        for (var i = 0; i < arguments.length; i++) {
                            console.log("  arg" + i + ": " + arguments[i]);
                        }
                        return overload.apply(this, arguments);
                    };
                });
            } catch(e) {}
        });

        // ============ Auth/Login Success ============
        try {
            var LoginOk = Java.use("com.avito.android.remote.model.LoginResult$Ok");
            LoginOk["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[LOGIN OK]");
                    for (var i = 0; i < arguments.length; i++) {
                        console.log("  arg" + i + ": " + arguments[i]);
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] LoginResult.Ok hooked");
        } catch(e) {}

        try {
            var AuthResult = Java.use("com.avito.android.remote.model.AuthResult");
            AuthResult["$init"].overloads.forEach(function(overload) {
                overload.implementation = function() {
                    console.log("\n[AUTH RESULT]");
                    for (var i = 0; i < arguments.length; i++) {
                        var arg = arguments[i];
                        if (arg && arg.toString) {
                            console.log("  arg" + i + ": " + arg.toString().substring(0, 500));
                        } else {
                            console.log("  arg" + i + ": " + arg);
                        }
                    }
                    return overload.apply(this, arguments);
                };
            });
            console.log("[+] AuthResult hooked");
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

        // ============ WebSocket ============
        try {
            var RealWebSocket = Java.use("okhttp3.internal.ws.RealWebSocket");

            RealWebSocket.send.overload('java.lang.String').implementation = function(text) {
                console.log("\n>>> WS: " + text.substring(0, 300));
                return this.send(text);
            };

            RealWebSocket.onReadMessage.overload('java.lang.String').implementation = function(text) {
                console.log("\n<<< WS: " + text.substring(0, 500));
                return this.onReadMessage(text);
            };
            console.log("[+] WebSocket hooked");
        } catch(e) {}

        // ============ SharedPreferences ============
        try {
            var Editor = Java.use("android.content.SharedPreferences$Editor");
            Editor.putString.implementation = function(key, value) {
                if (key && (key.indexOf("session") !== -1 || key.indexOf("token") !== -1 ||
                    key.indexOf("auth") !== -1 || key.indexOf("user") !== -1 ||
                    key.indexOf("refresh") !== -1 || key.indexOf("sessid") !== -1 ||
                    key.indexOf("captcha") !== -1 || key.indexOf("phone") !== -1)) {
                    console.log("\n[PREFS] " + key + " = " + (value ? value.substring(0, 200) : "null"));
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

        console.log("\n[*] Ready! Try login with captcha...\n");
    });
}, 1000);
