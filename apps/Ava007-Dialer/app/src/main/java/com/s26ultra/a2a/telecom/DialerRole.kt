package com.s26ultra.a2a.telecom

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context

/**
 * ROLE_DIALER helper.
 *
 * Not required for self-managed VoIP calls. Requesting it replaces the system
 * phone app for SIM calls too, so it is exposed only as an explicit opt-in.
 */
object DialerRole {

    const val REQUEST_CODE = 4107

    fun isAvailable(context: Context): Boolean {
        val roles = context.getSystemService(RoleManager::class.java) ?: return false
        return roles.isRoleAvailable(RoleManager.ROLE_DIALER)
    }

    fun isHeld(context: Context): Boolean {
        val roles = context.getSystemService(RoleManager::class.java) ?: return false
        return roles.isRoleAvailable(RoleManager.ROLE_DIALER) &&
            roles.isRoleHeld(RoleManager.ROLE_DIALER)
    }

    fun request(activity: Activity): Boolean {
        val roles = activity.getSystemService(RoleManager::class.java) ?: return false
        if (!roles.isRoleAvailable(RoleManager.ROLE_DIALER)) return false
        if (roles.isRoleHeld(RoleManager.ROLE_DIALER)) return true
        activity.startActivityForResult(
            roles.createRequestRoleIntent(RoleManager.ROLE_DIALER),
            REQUEST_CODE
        )
        return true
    }
}
