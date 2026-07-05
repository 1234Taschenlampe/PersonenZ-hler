package de.personenzaehler.mobile.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FormattingTest {
    @Test
    fun missingValuesAreNotRenderedAsZero() {
        assertEquals("N/A", formatInt(null))
        assertEquals("N/A", formatDouble(null))
        assertEquals("N/A", formatDuration(null))
    }

    @Test
    fun formatsDurationWithDays() {
        assertEquals("1 Tage 01:01:01", formatDuration(90_061.0))
    }

    @Test
    fun staleCalculationUsesLastSuccessTime() {
        assertTrue(isStale(null, nowMillis = 1000, maxAgeMillis = 100))
        assertTrue(isStale(0, nowMillis = 1000, maxAgeMillis = 100))
        assertFalse(isStale(950, nowMillis = 1000, maxAgeMillis = 100))
    }
}
