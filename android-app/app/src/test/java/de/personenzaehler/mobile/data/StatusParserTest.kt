package de.personenzaehler.mobile.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StatusParserTest {
    @Test
    fun parsesStatusWithMissingOptionalValues() {
        val status = StatusParser.parseStatus(
            """
            {
              "timestamp": 1780000000,
              "service": "visitor-counter",
              "version": {"server": "visitor-counter", "git_commit": "abc123"},
              "api": {"name": "visitor-counter-status-api", "version": "1"},
              "counts": {"inside": 2, "entered": 3, "exited": 1, "suppressed": 0, "uncertain": null},
              "cameras": [{"camera_id": "camera_1", "name": "Eingang", "status": "ONLINE", "width": 1280, "height": 720}],
              "detector": {"configured_model": "YOLO26m", "active": true, "hef_exists": true},
              "reid": {"configured_model": "OSNet", "ready": true},
              "hailo": {"device_detected": true, "architecture": "HAILO10H"},
              "host": {"cpu_percent": 12.5, "ram_percent": 44.0, "load_average": [0.1, 0.2]},
              "database": {"exists": true, "size_bytes": 1024}
            }
            """.trimIndent(),
        )

        assertEquals(2, status.counts.inside)
        assertNull(status.counts.uncertain)
        assertEquals("camera_1", status.cameras.single().cameraId)
        assertEquals("abc123", status.version.gitCommit)
    }

    @Test
    fun parsesEvents() {
        val events = StatusParser.parseEvents(
            """
            {"events":[{"event_id":1,"time":1780000000,"camera_id":"camera_1","direction":"in","event_type":"crossing","counted":true,"uncertain":false,"confidence":0.9}]}
            """.trimIndent(),
        )

        assertEquals(1, events.size)
        assertEquals("in", events.first().direction)
    }
}
