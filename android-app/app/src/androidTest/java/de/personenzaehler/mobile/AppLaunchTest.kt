package de.personenzaehler.mobile

import androidx.test.core.app.ActivityScenario
import org.junit.Test

class AppLaunchTest {
    @Test
    fun appStartsWithoutCrash() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                check(activity.packageName == "de.personenzaehler.mobile")
            }
        }
    }
}
