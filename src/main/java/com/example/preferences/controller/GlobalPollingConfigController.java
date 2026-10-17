package com.example.preferences.controller;

import com.example.preferences.service.GlobalPollingConfigService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/config")
public class GlobalPollingConfigController {
    private final GlobalPollingConfigService service;

    public GlobalPollingConfigController(GlobalPollingConfigService service) {
        this.service = service;
    }

    @PutMapping("/global-polling-interval")
    public ResponseEntity<?> update(@RequestBody Map<String, Integer> request) {
        Integer value = request.get("pollingIntervalSeconds");
        if (value == null) {
            return ResponseEntity.badRequest().body("pollingIntervalSeconds is required");
        }
        try {
            return ResponseEntity.ok(Map.of("pollingIntervalSeconds", service.update(value)));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(ex.getMessage());
        }
    }
}
