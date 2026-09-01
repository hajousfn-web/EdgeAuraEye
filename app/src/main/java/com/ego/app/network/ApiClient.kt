package com.ego.app.network

import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

// Placeholder واضح: استبدل هذا العنوان بعنوان السيرفر الحقيقي الخاص بك.
// مثال: http://192.168.1.25:8000/
private const val BASE_URL = "http://YOUR_SERVER_IP:8000/"

data class TelemetryPayload(
    val lat: Double,
    val lon: Double,
    val speed: Double,
    val distance: Double,
    val timestamp: Long
)

interface TelemetryApiService {
    @POST("api/telemetry")
    suspend fun sendTelemetry(@Body payload: TelemetryPayload): Response<Unit>
}

object ApiClient {
    private val okHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    val apiService: TelemetryApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(TelemetryApiService::class.java)
    }
}
