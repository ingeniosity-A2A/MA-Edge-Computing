package com.s26ultra.a2a.telecom

import android.net.Uri
import android.telecom.Connection
import android.telecom.PhoneAccount
import android.telecom.TelecomManager
import android.util.Log

/**
 * One self-managed VoIP call. The Telnyx session drives state changes through
 * [TelecomCallCoordinator].
 */
class A2AConnection(destination: String) : Connection() {

    init {
        setAddress(
            Uri.fromParts(PhoneAccount.SCHEME_TEL, destination, null),
            TelecomManager.PRESENTATION_ALLOWED
        )
        setConnectionProperties(PROPERTY_SELF_MANAGED)
        setConnectionCapabilities(CAPABILITY_MUTE or CAPABILITY_SUPPORT_HOLD)
        setAudioModeIsVoip(true)
        setInitializing()
    }

    override fun onDisconnect() {
        TelecomCallCoordinator.hangup()
    }

    override fun onAbort() {
        TelecomCallCoordinator.hangup()
    }

    override fun onReject() {
        TelecomCallCoordinator.hangup()
    }

    override fun onAnswer() {
        // Outgoing calls become ACTIVE when Telnyx reports CallState.ACTIVE.
        Log.d(TAG, "onAnswer")
    }

    override fun onHold() {
        // Holding is advertised only so the system UI has a stable capability
        // set; Telnyx hold is not wired up yet.
        Log.d(TAG, "onHold ignored")
    }

    override fun onUnhold() {
        Log.d(TAG, "onUnhold ignored")
    }

    companion object {
        private const val TAG = "A2AConnection"
    }
}
