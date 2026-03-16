// Wait for Java to be available
function waitForJava() {
    if (Java.available) {
        Java.perform(function() {
            send('[*] Java.perform started');

            // Find fingerprint classes
            try {
                Java.enumerateLoadedClasses({
                    onMatch: function(className) {
                        if (className.indexOf('libfp') !== -1 ||
                            (className.indexOf('Fingerprint') !== -1 && className.indexOf('avito') !== -1) ||
                            (className.indexOf('security') !== -1 && className.indexOf('avito') !== -1)) {
                            send('[CLASS] ' + className);
                        }
                    },
                    onComplete: function() {
                        send('[*] Class enumeration complete');
                    }
                });
            } catch(e) {
                send('[ERROR enumerating] ' + e);
            }

            // Hook System.loadLibrary
            try {
                var System = Java.use('java.lang.System');
                System.loadLibrary.overload('java.lang.String').implementation = function(libname) {
                    send('[loadLibrary] ' + libname);
                    return this.loadLibrary(libname);
                };
                send('[+] System.loadLibrary hooked');
            } catch(e) {
                send('[ERROR hooking] ' + e);
            }

            send('[*] Hooks installed');
        });
    } else {
        send('[*] Waiting for Java...');
        setTimeout(waitForJava, 500);
    }
}

send('[*] Script loaded');
waitForJava();
