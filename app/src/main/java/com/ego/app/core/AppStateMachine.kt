package com.ego.app

enum class AppState {
    IDLE,           // في حالة انتظار أو استماع للروابط والإحداثيات
    TRACKING,       // التتبع الجغرافي وحساب السرعة والمسافة نشط
    HAZARD_ACTIVE   // تم رصد خطر أو تفعيل الكاميرا ورفع البيانات للسيرفر
}

object AppStateMachine {
    private var currentState: AppState = AppState.IDLE

    fun transitionTo(newState: AppState): Boolean {
        if (currentState == newState) return false
        currentState = newState
        return true
    }

    fun getCurrentState(): AppState {
        return currentState
    }
}