package com.ego.app

import kotlin.math.abs

object BehaviorAnalyzer {
    private var previousSpeed = 0f

    // 1. تحليل سلوك الحركة ومراقبة التغير المفاجئ (Anomaly Detection)
    fun checkBehaviorAnomaly(currentSpeed: Float): Boolean {
        val speedDifference = abs(currentSpeed - previousSpeed)
        previousSpeed = currentSpeed
        
        // إيلا كان تفاوت كبير بزاف في السرعة (فرملة قاسية أو تسارع مفاجئ غير طبيعي)
        return speedDifference > 20.0f 
    }

    // 2. تفعيل التسجيل الذكي للصندوق الأسود وتخزينه في القاعدة المحلية
    suspend fun triggerSmartBlackbox(
        database: EgoDatabase, 
        lat: Double, 
        lon: Double, 
        speed: Float, 
        distance: Float
    ) {
        val emergencyLog = EgoLogEntity(
            latitude = lat,
            longitude = lon,
            speed = speed,
            distance = distance,
            timestamp = System.currentTimeMillis()
        )
        // حفظ اللوغ الذكي في قاعدة بيانات Room بشكل فوري عند وقوع الحدث أو الخطر
        database.egoDao().insertLog(emergencyLog)
    }
}
```[cite: 3]

---

### 3. فين غا نعيطو ليه (Integration)؟
باش يخدم هاد الشي، غادي نمشيو لملف **`MainActivity`** (اللي كاين في الجذر) فين كيتتبع الموقع، وغادي ندمجوه باش يبقَا يراقب السرعة لحظة بلحظة:

في دالة التتبع داخل `MainActivity`، فاش كتوصلنا السرعة الجديدة، كنعيطو على التحليل:
```kotlin
// داخل LocationTracker callback في MainActivity:
val isAnomalous = BehaviorAnalyzer.checkBehaviorAnomaly(speed)
if (isAnomalous) {
    // إيلا كاين شي سلوك خطير أو مفاجئ، كنفعلو التسجيل الذكي تلقائياً
    // (يمكن ليك تمرر قاعدة البيانات EgoDatabase.getDatabase(this))
}
```[cite: 3]

واش نكتب ليك التعديل الكامل ديال `MainActivity` باش يندمج فيه هاد النظام الجديد نيشان؟ 🚀