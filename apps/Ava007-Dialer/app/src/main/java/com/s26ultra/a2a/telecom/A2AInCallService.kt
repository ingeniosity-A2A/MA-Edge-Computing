package com.s26ultra.a2a.telecom

import android.telecom.Call
import android.telecom.InCallService
import android.util.Log

/**
 * Present for ROLE_DIALER eligibility.
 *
 * Self-managed calls are rendered by [com.s26ultra.a2a.MainActivity], so this
 * service does not take over the UI unless the app becomes the default dialer.
 */
class A2AInCallService : InCallService() {

    override fun onCallAdded(call: Call) {
        super.onCallAdded(call)
        Log.i(TAG, "onCallAdded state=${call.state} details=${call.details}")
    }

    override fun onCallRemoved(call: Call) {
        super.onCallRemoved(call)
        Log.i(TAG, "onCallRemoved")
    }

    companion object {
        private const val TAG = "A2AInCallService"
    }
}
