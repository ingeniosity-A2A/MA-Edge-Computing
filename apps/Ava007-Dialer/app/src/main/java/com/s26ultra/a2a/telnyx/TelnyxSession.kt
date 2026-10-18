package com.s26ultra.a2a.telnyx

import android.content.Context
import android.util.Log
import com.telnyx.webrtc.sdk.Call
import com.telnyx.webrtc.sdk.CredentialConfig
import com.telnyx.webrtc.sdk.TelnyxClient
import com.telnyx.webrtc.sdk.model.ConnectionStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

/**
 * Single process-wide Telnyx WebRTC session.
 *
 * The ConnectionService and the Activity live in the same process, so the
 * Telecom connection can drive the Telnyx call directly.
 */
object TelnyxSession {

    private const val TAG = "TelnyxSession"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private var client: TelnyxClient? = null
    private var statusJob: Job? = null

    @Volatile
    private var registered = false

    private var callerName: String = "S26 Ultra A2A"
    private var callerNumber: String = ""

    private val _status = MutableStateFlow("Not connected")
    val status: StateFlow<String> = _status.asStateFlow()

    fun login(
        context: Context,
        sipUser: String,
        sipPassword: String,
        callerNumber: String
    ) {
        if (sipUser.isBlank() || sipPassword.isBlank()) {
            _status.value = "SIP username and password are required"
            return
        }
        this.callerNumber = callerNumber
        disconnect()

        val appContext = context.applicationContext
        scope.launch {
            try {
                val newClient = TelnyxClient(appContext)
                client = newClient
                registered = false
                _status.value = "Connecting…"

                statusJob = launch {
                    newClient.connectionStatusFlow.collect { state ->
                        registered = state == ConnectionStatus.CLIENT_READY
                        _status.value = when (state) {
                            ConnectionStatus.CLIENT_READY -> "Registered as $sipUser"
                            ConnectionStatus.CONNECTED -> "Socket connected, registering…"
                            ConnectionStatus.RECONNECTING -> "Reconnecting…"
                            ConnectionStatus.DISCONNECTED -> "Disconnected"
                        }
                    }
                }

                newClient.connect(
                    credentialConfig = CredentialConfig(
                        sipUser = sipUser,
                        sipPassword = sipPassword,
                        sipCallerIDName = callerName,
                        sipCallerIDNumber = callerNumber.ifBlank { null },
                        fcmToken = null,
                        ringtone = null,
                        ringBackTone = null
                    ),
                    autoLogin = true
                )
            } catch (t: Throwable) {
                Log.e(TAG, "login failed", t)
                registered = false
                _status.value = "Login failed: ${t.message}"
            }
        }
    }

    fun disconnect() {
        statusJob?.cancel()
        statusJob = null
        registered = false
        runCatching { client?.disconnect() }
        client = null
        _status.value = "Not connected"
    }

    /**
     * Waits for CLIENT_READY, then sends the SIP INVITE. All results are
     * delivered asynchronously so the caller can return the Telecom
     * Connection to the framework first.
     */
    fun placeCall(
        destination: String,
        onCall: (Call) -> Unit,
        onError: (String) -> Unit
    ) {
        scope.launch {
            val active = client
            if (active == null) {
                onError("Not connected to Telnyx")
                return@launch
            }
            try {
                if (!registered) {
                    withTimeout(20_000) {
                        active.connectionStatusFlow.first { it == ConnectionStatus.CLIENT_READY }
                    }
                }
                val call = active.newInvite(
                    callerName,
                    callerNumber,
                    destination,
                    "a2a-outbound"
                )
                onCall(call)
            } catch (t: Throwable) {
                Log.e(TAG, "placeCall failed", t)
                onError(t.message ?: "Call setup failed")
            }
        }
    }

    fun endCall(callId: java.util.UUID) {
        runCatching { client?.endCall(callId) }
            .onFailure { Log.e(TAG, "endCall failed", it) }
    }

    fun isRegistered(): Boolean = registered
}
