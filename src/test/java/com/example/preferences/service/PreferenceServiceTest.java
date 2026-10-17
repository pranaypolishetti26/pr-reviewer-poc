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
    @Test
    void acceptsBothPollingIntervalBoundaries() {
        assertEquals(30, service.updatePreference("customer-1", 30).pollingIntervalSeconds());
        assertEquals(3600, service.updatePreference("customer-1", 3600).pollingIntervalSeconds());
    }

    @Test
    void invalidUpdatePreservesPreviousPreference() {
        service.updatePreference("customer-1", 120);
        assertThrows(IllegalArgumentException.class, () -> service.updatePreference("customer-1", 29));
        assertEquals(120, service.getPreference("customer-1").pollingIntervalSeconds());
    }
}
