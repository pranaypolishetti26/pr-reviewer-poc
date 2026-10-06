package com.example.preferences.service;

import com.example.preferences.model.PreferenceResponse;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class PreferenceService {
    public static final int MIN_POLLING_INTERVAL_SECONDS = 30;
    public static final int MAX_POLLING_INTERVAL_SECONDS = 3600;

    private final Map<String, Integer> pollingIntervals = new ConcurrentHashMap<>();

    public PreferenceResponse getPreference(String customerId) {
        int pollingInterval = pollingIntervals.getOrDefault(customerId, 300);
        return new PreferenceResponse(customerId, pollingInterval);
    }

    public PreferenceResponse updatePreference(String customerId, int pollingIntervalSeconds) {
        validatePollingInterval(pollingIntervalSeconds);
        pollingIntervals.put(customerId, pollingIntervalSeconds);
        return new PreferenceResponse(customerId, pollingIntervalSeconds);
    }

    private void validatePollingInterval(int pollingIntervalSeconds) {
        if (pollingIntervalSeconds < MIN_POLLING_INTERVAL_SECONDS || pollingIntervalSeconds > MAX_POLLING_INTERVAL_SECONDS) {
            throw new IllegalArgumentException("pollingIntervalSeconds must be between " + MIN_POLLING_INTERVAL_SECONDS + " and " + MAX_POLLING_INTERVAL_SECONDS);
        }
    }
}
