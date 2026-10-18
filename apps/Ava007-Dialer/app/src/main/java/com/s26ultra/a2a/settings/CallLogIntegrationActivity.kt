package com.s26ultra.a2a.settings

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Android 17 (API 37) can launch this activity through
 * android.telecom.action.CONFIGURE_CALL_LOG_INTEGRATION so the user can manage
 * whether this app writes VoIP calls into the system call log.
 */
class CallLogIntegrationActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val padding = (24 * resources.displayMetrics.density).toInt()
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }

        container.addView(
            TextView(this).apply {
                text = "Android 17 (API 37) lets you decide whether Ava007 may write " +
                    "VoIP calls into the system call log. Open the system settings below " +
                    "to review this app's call-log integration."
                textSize = 16f
            }
        )

        container.addView(
            Button(this).apply {
                text = "Open call log settings"
                setOnClickListener {
                    runCatching {
                        startActivity(Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS))
                    }
                }
            }
        )

        setContentView(container)
    }
}
