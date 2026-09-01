package com.ego.app

import android.content.Intent
import android.net.Uri

object DeepLinkHandler {
    data class Coordinates(val lat: Double, val lon: Double)

    fun parseIncomingLink(intent: Intent?): Coordinates? {
        val uri: Uri = intent?.data ?: return null
        
        val lat = uri.getQueryParameter("lat")?.toDoubleOrNull()
        val lon = uri.getQueryParameter("lon")?.toDoubleOrNull()

        if (lat != null && lon != null) {
            return Coordinates(lat, lon)
        }
        return null
    }
}