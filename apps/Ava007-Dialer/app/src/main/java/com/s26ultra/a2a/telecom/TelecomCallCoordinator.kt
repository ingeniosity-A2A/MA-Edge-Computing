package com.s26ultra.a2a.telecom

import android.telecom.DisconnectCause
import android.util.Log
import com.s26ultra.a2a.telnyx.TelnyxSession
import com.telnyx.webrtc.sdk.Call
import com.telnyx.webrtc.sdk.model.CallState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Owns the single in-flight call and mirrors Telnyx call state onto the
 * Telecom [A2AConnection].
 */
object TelecomCallCoordinator {

    private const val TAG = "TelecomCoordinator"

    sealed interface State {
        data object Idle : State
        data class Dialing(val number: String) : State
        data object Active : State
        data class Ended(val reason: String) : State
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    private var connection: A2AConnection? = null
    private var call: Call? = null
    private var watcher: Job? = null
    private var terminated = true
    private var localHangup = false

    fun onOutgoingConnectionCreated(conn: A2AConnection, number: String) {
        watcher?.cancel()
        connection = conn
        call = null
        terminated = false
        localHangup = false
        _state.value = State.Dialing(number)

        // The Connection must be returned to Telecom before state changes land.
        scope.launch { if (!terminated) conn.setDialing() }

        TelnyxSession.placeCall(
            destination = number,
            onCall = { telnyxCall ->
                call = telnyxCall
                watch(telnyxCall)
            },
            onError = { message -> terminate(message, DisconnectCause.ERROR) }
        )
    }

    fun failSetup(message: String) {
        terminate(message, DisconnectCause.ERROR)
    }

    private fun watch(telnyxCall: Call) {
        watcher?.cancel()
        watcher = scope.launch {
            telnyxCall.callStateFlow.collect { callState ->
                when (callState) {
                    CallState.ACTIVE -> {
                        if (!terminated) {
                            connection?.setActive()
                            _state.value = State.Active
                        }
                    }

                    is CallState.DONE -> {
                        val cause = if (localHangup) DisconnectCause.LOCAL else DisconnectCause.REMOTE
                        terminate("Call ended", cause)
                    }

                    CallState.ERROR -> terminate("Telnyx call error", DisconnectCause.ERROR)
                    else -> Unit
                }
            }
        }
    }

    fun hangup() {
        if (terminated) return
        localHangup = true
        call?.let { TelnyxSession.endCall(it.callId) }
        scope.launch {
            delay(3_000)
            terminate("Call ended", DisconnectCause.LOCAL)
        }
    }

    private fun terminate(reason: String, causeCode: Int) {
        if (terminated) return
        terminated = true
        watcher?.cancel()
        watcher = null

        val activeConnection = connection
        connection = null
        call = null

        activeConnection?.let {
            val cause = if (causeCode == DisconnectCause.ERROR) {
                DisconnectCause(causeCode, reason)
            } else {
                DisconnectCause(causeCode)
            }
            it.setDisconnected(cause)
            it.destroy()
        }
        _state.value = State.Ended(reason)
        Log.i(TAG, "call terminated: $reason ($causeCode)")
    }
}
