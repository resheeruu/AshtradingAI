# AshtradingAI ProGuard Rules

# Gson
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.ashtradingai.data.model.** { *; }
-keep class com.google.gson.** { *; }

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
