# Add project specific ProGuard rules here.

# Keep data classes
-keep class com.avitobridge.data.** { *; }

# Keep Gson
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.google.gson.** { *; }

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# libsu
-keep class com.topjohnwu.superuser.** { *; }
