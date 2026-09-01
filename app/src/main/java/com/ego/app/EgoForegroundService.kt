package com.ego.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class EgoForegroundService : Service() {

    companion object {
        private const val CHANNEL_ID = "EgoForegroundServiceChannel"
        private const val NOTIFICATION_ID = 1001
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // إنشاء إشعار مستمر لإبقاء الخدمة تعمل في الخلفية بشكل قانوني وآمن حسب نظام أندرويد
        val notificationIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            notificationIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("نظام Ego الذكي يعمل في الخلفية")
            .setContentText("جاري مراقبة السرعة والملاحة والتحليل اللحظي للسلامة...")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation) // يمكن استبدالها بأيقونة التطبيق المخصصة لاحقاً
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()

        // بدء الخدمة في الأمامية مع تحديد نوع الصلاحية برمجياً لضمان عدم انهيار التطبيق في الأنظمة الحديثة
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // دمج صلاحية الموقع لضمان استمرار عمل الـ GPS في الخلفية بأمان
            startForeground(
                NOTIFICATION_ID, 
                notification, 
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        // إذا تم إيقاف التطبيق قسراً، نسمح للنظام بإعادة تشغيل الخدمة تلقائياً
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        // هذه الخدمة لا توفر ربطاً مباشراً (Bound Service)، لذا نعيد null
        return null
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "Ego Background Navigation Channel",
                NotificationManager.IMPORTANCE_LOW // أهمية منخفضة لكي لا يزعج المستخدم بإشعارات صوتية متكررة
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(serviceChannel)
        }
    }
}