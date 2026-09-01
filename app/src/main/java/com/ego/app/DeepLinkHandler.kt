package com.ego.app

import android.content.Intent
import android.net.Uri
import android.util.Log

// كلاس مساعد لتمثيل الإحداثيات المستخرجة من الرابط العميق
data class DeepLinkCoordinates(
    val lat: Double,
    val lon: Double
)

object DeepLinkHandler {

    /**
     * وظيفتها قراءة الـ Intent والبحث عن أي إحداثيات قادمة عبر Deep Link
     * الرابط المتوافق مع الـ Manifest: ego://trigger?lat=33.5731&lon=-7.5898
     */
    fun parseIncomingLink(intent: Intent?): DeepLinkCoordinates? {
        val uri: Uri? = intent?.data
        if (uri != null) {
            // التصحيح: التحقق الصارم من الـ scheme والـ host لضمان مطابقة الـ Manifest والأمان
            if (uri.scheme == "ego" && uri.host == "trigger") {
                try {
                    val latStr = uri.getQueryParameter("lat")
                    val lonStr = uri.getQueryParameter("lon")

                    if (!latStr.isNullOrEmpty() && !lonStr.isNullOrEmpty()) {
                        // فلترة وتنقية البيانات أثناء التحويل لمنع القيم التالفة
                        val lat = latStr.toDouble()
                        val lon = lonStr.toDouble()
                        
                        Log.d("Ego_DeepLink", "تم استقبال إحداثيات ملاحة خارجية بنجاح: $lat, $lon")
                        return DeepLinkCoordinates(lat, lon)
                    }
                } catch (e: Exception) {
                    Log.e("Ego_DeepLink", "خطأ في معالجة أو تحويل أرقام الإحداثيات الجغرافية: ${e.message}")
                }
            }
        }
        return null
    }
}