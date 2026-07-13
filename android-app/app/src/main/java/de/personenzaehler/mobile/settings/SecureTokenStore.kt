package de.personenzaehler.mobile.settings

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class SecureTokenStore(context: Context) {
    private val prefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "secure_server_token",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    fun readToken(): String? = prefs.getString(KEY_TOKEN, null)?.takeIf { it.isNotBlank() }

    fun saveToken(token: String) {
        val normalized = token.trim()
        require(normalized.length >= 32) { "Token must contain at least 32 characters" }
        prefs.edit().putString(KEY_TOKEN, normalized).apply()
    }

    fun clearToken() {
        prefs.edit().remove(KEY_TOKEN).apply()
    }

    private companion object {
        const val KEY_TOKEN = "bearer_token"
    }
}
