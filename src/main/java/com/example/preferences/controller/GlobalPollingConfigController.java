package com.example.preferences.controller;

import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/config")
public class GlobalPollingConfigController {
    private int globalPollingIntervalSeconds = 300;

    @PutMapping("/global-polling-interval")
    public Map<String, Integer> updateGlobalPollingInterval(@RequestBody Map<String, Integer> request) {
        globalPollingIntervalSeconds = request.get("pollingIntervalSeconds");
        return Map.of("pollingIntervalSeconds", globalPollingIntervalSeconds);
    }
}
