package com.s26ultra.a2a

import android.app.Application
import com.s26ultra.a2a.telecom.VoIPAccountManager

class A2AApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        VoIPAccountManager.ensureRegistered(this)
    }
}
