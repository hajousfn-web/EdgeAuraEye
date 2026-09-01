package com.ego.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import com.ego.app.network.ApiClient
import com.ego.app.network.TelemetryPayload
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import retrofit2.Response

object SyncManager {

    private const val MAX_RETRIES = 3

    // 1. فحص واش كاين اتصال بالإنترنت ولا لأ
    fun isNetworkAvailable(context: Context): Boolean {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val network = connectivityManager.activeNetwork ?: return false
            val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
            return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        } else {
            val networkInfo = connectivityManager.activeNetworkInfo
            return networkInfo != null && networkInfo.isConnected
        }
    }

    // 2. دالة إرسال البيانات (Online First مع حفظ احتياطي إذا وقع قطع)
    suspend fun syncDataToServer(
        context: Context,
        database: EgoDatabase,
        lat: Double,
        lon: Double,
        speed: Float,
        distance: Float
    ): Boolean {
        return withContext(Dispatchers.IO) {
            if (!isNetworkAvailable(context)) {
                saveToLocalBlackbox(database, lat, lon, speed, distance)
                return@withContext false
            }

            try {
                val payload = TelemetryPayload(
                    lat = lat,
                    lon = lon,
                    speed = speed.toDouble(),
                    distance = distance.toDouble(),
                    timestamp = System.currentTimeMillis()
                )

                val response: Response<Unit> = ApiClient.apiService.sendTelemetry(payload)
                if (response.isSuccessful) {
                    return@withContext true
                }

                saveToLocalBlackbox(database, lat, lon, speed, distance)
                return@withContext false
            } catch (e: Exception) {
                saveToLocalBlackbox(database, lat, lon, speed, distance)
                return@withContext false
            }
        }
    }

    // 3. التخزين المؤقت في قاعدة البيانات المحلية (Room)
    private suspend fun saveToLocalBlackbox(
        database: EgoDatabase,
        lat: Double,
        lon: Double,
        speed: Float,
        distance: Float
    ) {
        val logEntity = EgoLogEntity(
            latitude = lat,
            longitude = lon,
            speed = speed,
            distance = distance,
            timestamp = System.currentTimeMillis()
        )
        database.egoDao().insertLog(logEntity)
    }

    // 4. دالة المزامنة التلقائية (Bulk Sync) فاش ترجع الكونيكسيون
    suspend fun flushOfflineQueue(context: Context, database: EgoDatabase) {
        if (!isNetworkAvailable(context)) {
            return
        }

        withContext(Dispatchers.IO) {
            val dao = database.egoDao()
            val pendingLogs = dao.getAllLogs()

            for (log in pendingLogs) {
                var attempt = 0
                var sentSuccessfully = false

                while (attempt < MAX_RETRIES && !sentSuccessfully) {
                    try {
                        val response = ApiClient.apiService.sendTelemetry(
                            TelemetryPayload(
                                lat = log.latitude,
                                lon = log.longitude,
                                speed = log.speed.toDouble(),
                                distance = log.distance.toDouble(),
                                timestamp = log.timestamp
                            )
                        )

                        if (response.isSuccessful) {
                            dao.deleteLog(log.id)
                            sentSuccessfully = true
                        } else {
                            if (attempt < MAX_RETRIES - 1) {
                                val backoffMs = 2000L * (1 shl attempt)
                                delay(backoffMs)
                            }
                        }
                    } catch (e: Exception) {
                        if (attempt < MAX_RETRIES - 1) {
                            val backoffMs = 2000L * (1 shl attempt)
                            delay(backoffMs)
                        }
                    }

                    attempt += 1
                }

                // نترك السجل في Room إذا فشل بعد كل المحاولات، حتى تنجح المزامنة لاحقاً
            }
        }
    }
}