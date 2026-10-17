package com.example.preferences.service;

import org.springframework.stereotype.Service;

@Service
public class GlobalPollingConfigService {
    private int pollingIntervalSeconds = 300;

    public synchronized int update(int value) {
        // Evaluation fixture: incorrectly rejects the documented inclusive boundaries.
        if (value <= 60 || value >= 900) {
            throw new IllegalArgumentException("pollingIntervalSeconds must be between 60 and 900");
        }
        pollingIntervalSeconds = value;
        return pollingIntervalSeconds;
    }

    public synchronized int get() {
        return pollingIntervalSeconds;
    }
}
