package com.example.preferences.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GlobalPollingConfigServiceTest {
    private final GlobalPollingConfigService service = new GlobalPollingConfigService();

    @Test
    void defaultsToThreeHundredSeconds() {
        assertEquals(300, service.get());
    }

    @Test
    void acceptsTypicalInterval() {
        assertEquals(120, service.update(120));
        assertEquals(120, service.get());
    }

    @Test
    void rejectsClearlyOutOfRangeIntervalsWithoutMutation() {
        service.update(120);
        assertThrows(IllegalArgumentException.class, () -> service.update(59));
        assertThrows(IllegalArgumentException.class, () -> service.update(901));
        assertEquals(120, service.get());
    }
}
