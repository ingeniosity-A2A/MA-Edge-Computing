package com.s26ultra.a2a

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.textfield.TextInputEditText
import com.s26ultra.a2a.telecom.DialerRole
import com.s26ultra.a2a.telecom.TelecomCallCoordinator
import com.s26ultra.a2a.telecom.VoIPAccountManager
import com.s26ultra.a2a.telnyx.TelnyxSession
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var etSipUser: TextInputEditText
    private lateinit var etSipPassword: TextInputEditText
    private lateinit var etCallerId: TextInputEditText
    private lateinit var etDestination: TextInputEditText
    private lateinit var btnConnect: Button
    private lateinit var btnCall: Button
    private lateinit var btnEnd: Button
    private lateinit var btnDialerRole: Button
    private lateinit var tvStatus: TextView
    private lateinit var tvCallState: TextView

    private var pendingNumber: String? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val micGranted = grants[Manifest.permission.RECORD_AUDIO] == true || hasMicPermission()
        if (micGranted) {
            pendingNumber?.let { placeCall(it) }
        } else {
            toast("Microphone permission is required for VoIP audio")
        }
        pendingNumber = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        bindViews()

        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        etSipUser.setText(prefs.getString(KEY_SIP_USER, ""))
        etCallerId.setText(prefs.getString(KEY_CALLER_ID, DEFAULT_CALLER_ID))

        if (!VoIPAccountManager.ensureRegistered(this)) {
            toast("Self-managed phone account registration failed")
        }

        wireActions()
        observeState()
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        btnDialerRole.text = if (DialerRole.isHeld(this)) {
            "Default dialer role: held"
        } else {
            "Request default-dialer role (optional)"
        }
    }

    private fun bindViews() {
        etSipUser = findViewById(R.id.etSipUser)
        etSipPassword = findViewById(R.id.etSipPassword)
        etCallerId = findViewById(R.id.etCallerId)
        etDestination = findViewById(R.id.etDestination)
        btnConnect = findViewById(R.id.btnConnect)
        btnCall = findViewById(R.id.btnCall)
        btnEnd = findViewById(R.id.btnEnd)
        btnDialerRole = findViewById(R.id.btnDialerRole)
        tvStatus = findViewById(R.id.tvStatus)
        tvCallState = findViewById(R.id.tvCallState)
    }

    private fun wireActions() {
        btnConnect.setOnClickListener {
            val user = textOf(etSipUser)
            val password = textOf(etSipPassword)
            val callerId = textOf(etCallerId)
            if (user.isBlank() || password.isBlank()) {
                toast("Enter the SIP username and password from your Telnyx credential connection")
                return@setOnClickListener
            }
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putString(KEY_SIP_USER, user)
                .putString(KEY_CALLER_ID, callerId)
                .apply()
            TelnyxSession.login(this, user, password, callerId)
        }

        btnCall.setOnClickListener {
            val number = normalize(textOf(etDestination))
            if (number.length < 3) {
                toast("Enter a destination number")
                return@setOnClickListener
            }
            if (!TelnyxSession.isRegistered()) {
                toast("Tap Connect to register with Telnyx first")
                return@setOnClickListener
            }
            if (hasMicPermission()) {
                placeCall(number)
            } else {
                pendingNumber = number
                permissionLauncher.launch(requiredPermissions())
            }
        }

        btnEnd.setOnClickListener { TelecomCallCoordinator.hangup() }

        btnDialerRole.setOnClickListener {
            if (DialerRole.isHeld(this)) {
                toast("This app already holds ROLE_DIALER")
                return@setOnClickListener
            }
            AlertDialog.Builder(this)
                .setTitle("Replace the system dialer?")
                .setMessage(
                    "Self-managed VoIP calls already bypass the carrier dialer without this role. " +
                        "ROLE_DIALER makes this app handle ordinary SIM calls too, including their " +
                        "in-call UI. Only continue if that is what you want."
                )
                .setPositiveButton("Request role") { _, _ ->
                    if (!DialerRole.request(this)) toast("Dialer role is unavailable on this device")
                }
                .setNegativeButton("Cancel", null)
                .show()
        }
    }

    private fun observeState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { TelnyxSession.status.collect { tvStatus.text = it } }
                launch { TelecomCallCoordinator.state.collect { render(it) } }
            }
        }
    }

    private fun render(state: TelecomCallCoordinator.State) {
        when (state) {
            TelecomCallCoordinator.State.Idle -> {
                tvCallState.text = "Idle"
                btnEnd.isEnabled = false
                btnCall.isEnabled = true
            }

            is TelecomCallCoordinator.State.Dialing -> {
                tvCallState.text = "Dialing ${state.number}…"
                btnEnd.isEnabled = true
                btnCall.isEnabled = false
            }

            TelecomCallCoordinator.State.Active -> {
                tvCallState.text = "In call (VoIP)"
                btnEnd.isEnabled = true
                btnCall.isEnabled = false
            }

            is TelecomCallCoordinator.State.Ended -> {
                tvCallState.text = "Ended: ${state.reason}"
                btnEnd.isEnabled = false
                btnCall.isEnabled = true
            }
        }
    }

    private fun placeCall(number: String) {
        VoIPAccountManager.placeCall(this, number)
            .onFailure { toast("Telecom rejected the call: ${it.message}") }
    }

    private fun handleIntent(intent: Intent?) {
        when (intent?.action) {
            Intent.ACTION_DIAL, Intent.ACTION_VIEW -> {
                intent.data?.schemeSpecificPart?.takeIf { it.isNotBlank() }?.let {
                    etDestination.setText(it)
                }
            }
        }
    }

    private fun requiredPermissions(): Array<String> {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CALL_PHONE
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions += Manifest.permission.POST_NOTIFICATIONS
        }
        return permissions.toTypedArray()
    }

    private fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    private fun normalize(raw: String): String {
        val trimmed = raw.trim()
        if (trimmed.startsWith("+")) return "+" + trimmed.drop(1).filter { it.isDigit() }
        val digits = trimmed.filter { it.isDigit() }
        return if (trimmed.startsWith("00")) "+" + digits.drop(2) else digits
    }

    private fun textOf(view: TextInputEditText): String = view.text?.toString()?.trim().orEmpty()

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    companion object {
        private const val PREFS = "a2a"
        private const val KEY_SIP_USER = "sip_user"
        private const val KEY_CALLER_ID = "caller_id"
        private const val DEFAULT_CALLER_ID = "+14044391350"
    }
}
