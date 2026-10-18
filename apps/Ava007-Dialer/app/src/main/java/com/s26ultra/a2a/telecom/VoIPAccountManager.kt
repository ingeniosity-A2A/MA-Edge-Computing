package com.s26ultra.a2a.telecom

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.telecom.PhoneAccount
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import android.util.Log
import com.s26ultra.a2a.R

/**
 * Registers a self-managed [PhoneAccount].
 *
 * A self-managed account is deliberately NOT combined with
 * [PhoneAccount.CAPABILITY_CALL_PROVIDER]: Android's own CTS rejects that
 * combination. Self-managed calls are owned by this app and never enter the
 * carrier dialer, and they do not require ROLE_DIALER.
 */
object VoIPAccountManager {

    private const val TAG = "VoIPAccountManager"
    const val ACCOUNT_ID = "a2a_voip_account"

    fun handle(context: Context): PhoneAccountHandle =
        PhoneAccountHandle(
            ComponentName(context, A2AConnectionService::class.java),
            ACCOUNT_ID
        )

    fun ensureRegistered(context: Context): Boolean {
        val telecom = context.getSystemService(TelecomManager::class.java) ?: return false
        val handle = handle(context)
        if (telecom.getPhoneAccount(handle) != null) return true

        val account = PhoneAccount.builder(handle, context.getString(R.string.account_label))
            .setCapabilities(PhoneAccount.CAPABILITY_SELF_MANAGED)
            .addSupportedUriScheme(PhoneAccount.SCHEME_TEL)
            .setShortDescription(context.getString(R.string.account_short_description))
            .build()

        return try {
            telecom.registerPhoneAccount(account)
            telecom.getPhoneAccount(handle) != null
        } catch (e: SecurityException) {
            Log.e(TAG, "registerPhoneAccount denied", e)
            false
        } catch (e: IllegalArgumentException) {
            Log.e(TAG, "PhoneAccount rejected", e)
            false
        }
    }

    /**
     * Places the call through Telecom. Telecom binds [A2AConnectionService] and
     * asks it for an outgoing [android.telecom.Connection].
     */
    fun placeCall(context: Context, number: String): Result<Unit> = runCatching {
        val telecom = context.getSystemService(TelecomManager::class.java)
            ?: error("Telecom service unavailable")
        check(ensureRegistered(context)) { "Self-managed PhoneAccount is not registered" }

        val uri = Uri.fromParts(PhoneAccount.SCHEME_TEL, number, null)
        val extras = Bundle().apply {
            putParcelable(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE, handle(context))
        }
        telecom.placeCall(uri, extras)
    }

    fun isRegistered(context: Context): Boolean {
        val telecom = context.getSystemService(TelecomManager::class.java) ?: return false
        return telecom.getPhoneAccount(handle(context)) != null
    }
}
