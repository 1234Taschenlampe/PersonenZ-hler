package de.personenzaehler.mobile.data

import org.junit.Assert.assertEquals
import org.junit.Test

class EventFilterTest {
    @Test
    fun eventFilterLabelsAreGermanAndStable() {
        assertEquals("Alle", EventFilter.All.label)
        assertEquals("Uncertain", EventFilter.Uncertain.label)
        assertEquals(6, EventFilter.entries.size)
    }
}
