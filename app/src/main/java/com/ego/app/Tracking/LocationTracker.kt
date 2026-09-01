package com.ego.app

import android.content.Context
import android.location.Location
import com.google.android.gms.location.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class LocationTracker(
    private val context: Context,
    private val onLocationUpdate: (Float, Float) -> Unit
) {

    private val fusedLocationClient: FusedLocationProviderClient = LocationServices.getFusedLocationProviderClient(context)
    private lateinit var locationCallback: LocationCallback
    private var totalDistanceMeters: Float = 0f
    private var lastLocation: Location? = null // تصحيح الخطأ هنا

    // سياق لتنفيذ مهام قاعدة البيانات في الخلفية
    private val scope = CoroutineScope(Dispatchers.IO)
    private val egoDao = EgoDatabase.getDatabase(context).egoDao()

    fun startTracking() {
        val locationRequest = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 2000)
            .setMinUpdateDistanceMeters(1f)
            .build()

        locationCallback = object : LocationCallback() {
            override fun onLocationResult(locationResult: LocationResult) {
                for (location in locationResult.locations) {
                    lastLocation?.let { prev ->
                        totalDistanceMeters += prev.distanceTo(location)
                    }
                    lastLocation = location

                    val speedKmh = location.speed * 3.6f
                    val distanceKm = totalDistanceMeters / 1000f

                    // 1. حفظ الداتا محلياً في SQLite/Room في الخلفية
                    scope.launch {
                        egoDao.insertLog(
                            EgoLogEntity(
                                latitude = location.latitude,
                                longitude = location.longitude,
                                speed = speedKmh,
                                distance = distanceKm
                            )
                        )
                    }

                    // 2. إرسال البيانات للواجهة آنياً
                    onLocationUpdate(distanceKm, speedKmh)
                }
            }
        }

        try {
            fusedLocationClient.requestLocationUpdates(locationRequest, locationCallback, null)
        } catch (e: SecurityException) {
            e.printStackTrace()
        }
    }

    fun stopTracking() {
        fusedLocationClient.removeLocationUpdates(locationCallback)
    }
}