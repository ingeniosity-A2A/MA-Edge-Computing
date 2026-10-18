package com.s26ultra.a2a.telecom

import android.telecom.Connection
import android.telecom.ConnectionRequest
import android.telecom.ConnectionService
import android.telecom.DisconnectCause
import android.telecom.PhoneAccountHandle
import android.util.Log

class A2AConnectionService : ConnectionService() {

    override fun onCreateOutgoingConnection(
        connectionManagerPhoneAccount: PhoneAccountHandle?,
        request: ConnectionRequest
    ): Connection {
        val number = request.address?.schemeSpecificPart.orEmpty()
        Log.i(TAG, "onCreateOutgoingConnection $number")
        val connection = A2AConnection(number)
        TelecomCallCoordinator.onOutgoingConnectionCreated(connection, number)
        return connection
    }

    override fun onCreateOutgoingConnectionFailed(
        connectionManagerPhoneAccount: PhoneAccountHandle?,
        request: ConnectionRequest
    ) {
        Log.w(TAG, "onCreateOutgoingConnectionFailed ${request.address}")
        TelecomCallCoordinator.failSetup("Telecom could not create the outgoing connection")
    }

    override fun onCreateIncomingConnection(
        connectionManagerPhoneAccount: PhoneAccountHandle?,
        request: ConnectionRequest
    ): Connection {
        // Incoming Telnyx invites are not bridged into Telecom yet.
        return Connection.createFailedConnection(
            DisconnectCause(DisconnectCause.ERROR, "Incoming calls are not implemented")
        )
    }

    companion object {
        private const val TAG = "A2AConnectionService"
    }
}
