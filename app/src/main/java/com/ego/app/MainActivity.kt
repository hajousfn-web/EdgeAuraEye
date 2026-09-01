package com.ego.app

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var database: EgoDatabase

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // 1. تهيئة قاعدة البيانات المحلية Room
        database = EgoDatabase.getDatabase(this)

        // 2. تفعيل الخدمة الأمامية (Foreground Service) باش التطبيق ما يطفاش في الخلفية
        val serviceIntent = Intent(this, EgoForegroundService::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }

        // 3. التحقق واش التطبيق تحل عبر Deep Link (إحداثيات خارجية)
        handleIncomingIntent(intent)

        // 4. تغيير حالة التطبيق إلى التتبع (TRACKING) عبر StateMachine
        AppStateMachine.transitionTo(AppState.TRACKING)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    // معالجة الروابط القادمة وإحداثيات الإطلاق
    private fun handleIncomingIntent(intent: Intent?) {
        val coordinates = DeepLinkHandler.parseIncomingLink(intent)
        if (coordinates != null) {
            // إليا جات إحداثيات جديدة عبر الرابط، كنفعلو حالة الخطر أو التوجيه
            AppStateMachine.transitionTo(AppState.HAZARD_ACTIVE)
            
            // مثال: إرسالها مباشرة عبر SyncManager
            lifecycleScope.launch {
                SyncManager.syncDataToServer(
                    context = this@MainActivity,
                    database = database,
                    lat = coordinates.lat,
                    lon = coordinates.lon,
                    speed = 0f,
                    distance = 0f
                )
            }
        }
    }

    // محاكاة استقبال بيانات جديدة من LocationTracker
    fun onNewLocationDataReceived(lat: Double, lon: Double, speed: Float, distance: Float) {
        // التحقق واش كاين سلوك خطير أو تسارع مفاجئ (Anomaly Detection)
        val isAnomalous = BehaviorAnalyzer.checkBehaviorAnomaly(speed)
        
        if (isAnomalous) {
            AppStateMachine.transitionTo(AppState.HAZARD_ACTIVE)
        }

        // إرسال البيانات للسيستم ( Online First مع حفظ احتياطي في Room إيلا تقطعت الكونيكسيون )
        lifecycleScope.launch {
            SyncManager.syncDataToServer(
                context = this,
                database = database,
                lat = lat,
                lon = lon,
                speed = speed,
                distance = distance
            )
            
            // محاولة مزامنة الداتا القديمة لي كانت متخزنة أوفلاين إيلا رجعت الشبكة
            SyncManager.flushOfflineQueue(this@MainActivity, database)
        }
    }
}