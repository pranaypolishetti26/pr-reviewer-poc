package com.example.preferences.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PreferenceServiceTest {
    private final PreferenceService service = new PreferenceService();

    @Test
    void updatesValidPollingInterval() {
        var response = service.updatePreference("customer-1", 120);
        assertEquals(120, response.pollingIntervalSeconds());
    }

    @Test
    void rejectsPollingIntervalBelowMinimum() {
        assertThrows(IllegalArgumentException.class, () -> service.updatePreference("customer-1", 10));
    }

    @Test
    void rejectsPollingIntervalAboveMaximum() {
        assertThrows(IllegalArgumentException.class, () -> service.updatePreference("customer-1", 5000));
    }
}
