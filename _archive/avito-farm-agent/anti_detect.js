// Anti-Frida detection bypass
// Hooks native functions to hide Frida presence before Java VM starts.
// Must be loaded FIRST, before any Java.perform hooks.

(function() {
    "use strict";

    // === 1. Hook libc open/openat to filter /proc/self/maps reads ===
    // Avito reads /proc/self/maps looking for "frida" strings
    try {
        var popen = Module.findExportByName("libc.so", "popen");
        if (popen) {
            Interceptor.attach(popen, {
                onEnter: function(args) {
                    var cmd = args[0].readUtf8String();
                    if (cmd && (cmd.indexOf("frida") !== -1 || cmd.indexOf("27042") !== -1)) {
                        send("[antidetect] popen blocked: " + cmd);
                        // Replace with harmless command
                        args[0].writeUtf8String("echo");
                    }
                }
            });
        }
    } catch(e) {}

    // === 2. Hook strstr to hide "frida" in memory scans ===
    try {
        var strstr = Module.findExportByName("libc.so", "strstr");
        if (strstr) {
            Interceptor.attach(strstr, {
                onEnter: function(args) {
                    this.haystack = args[0];
                    this.needle = args[1];
                    if (this.needle.isNull()) return;
                    try {
                        var needle = this.needle.readUtf8String();
                        if (needle === "frida" || needle === "LIBFRIDA" ||
                            needle === "frida-agent" || needle === "frida-server" ||
                            needle === "gmain" || needle === "gum-js-loop" ||
                            needle === "linjector") {
                            this.shouldBlock = true;
                        }
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    if (this.shouldBlock) {
                        retval.replace(ptr(0));
                    }
                }
            });
        }
    } catch(e) {}

    // === 3. Hook pthread_create to block Frida detection threads ===
    // Some apps spawn threads that continuously scan for Frida
    // We don't block all threads, just ones with suspicious start routines

    // === 4. Hook /proc/self/maps reads to filter "frida" lines ===
    try {
        var openPtr = Module.findExportByName("libc.so", "open");
        var readPtr = Module.findExportByName("libc.so", "read");
        var maps_fd = -1;

        if (openPtr) {
            Interceptor.attach(openPtr, {
                onEnter: function(args) {
                    try {
                        var path = args[0].readUtf8String();
                        if (path && (path === "/proc/self/maps" || path === "/proc/self/status" ||
                            path.indexOf("/proc/") !== -1 && path.indexOf("/maps") !== -1)) {
                            this.is_maps = true;
                        }
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    if (this.is_maps) {
                        maps_fd = retval.toInt32();
                    }
                }
            });
        }
    } catch(e) {}

    // === 5. Hook connect() to block connections to Frida port ===
    try {
        var connect = Module.findExportByName("libc.so", "connect");
        if (connect) {
            Interceptor.attach(connect, {
                onEnter: function(args) {
                    var sockaddr = args[1];
                    // AF_INET = 2
                    var family = sockaddr.readU16();
                    if (family === 2) {
                        var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
                        // Block connections to Frida default port and our custom port
                        if (port === 27042) {
                            send("[antidetect] connect to port " + port + " blocked");
                            this.block = true;
                        }
                    }
                },
                onLeave: function(retval) {
                    if (this.block) {
                        retval.replace(ptr(-1));
                    }
                }
            });
        }
    } catch(e) {}

    // === 6. Replace frida-related strings in /proc/self/maps response ===
    // Hook fgets which is commonly used to read maps line by line
    try {
        var fgets = Module.findExportByName("libc.so", "fgets");
        if (fgets) {
            Interceptor.attach(fgets, {
                onLeave: function(retval) {
                    if (retval.isNull()) return;
                    try {
                        var line = retval.readUtf8String();
                        if (line && (line.indexOf("frida") !== -1 || line.indexOf("gadget") !== -1 ||
                                     line.indexOf("gmain") !== -1 || line.indexOf("linjector") !== -1)) {
                            // Return empty/harmless line
                            retval.writeUtf8String("00000000-00000000 --- 0 00:00 0\n");
                        }
                    } catch(e) {}
                }
            });
        }
    } catch(e) {}

    send("[antidetect] Native anti-detection hooks installed");
})();

// Now wait for Java VM and load the Java hooks
function waitForJava(callback, attempts) {
    attempts = attempts || 0;
    if (typeof Java !== 'undefined' && Java.available) {
        callback();
    } else if (attempts < 50) {
        setTimeout(function() { waitForJava(callback, attempts + 1); }, 100);
    } else {
        send("[!] Java VM not available after 5 seconds");
    }
}
