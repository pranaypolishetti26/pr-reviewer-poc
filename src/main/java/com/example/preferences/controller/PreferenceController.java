package com.example.preferences.controller;

import com.example.preferences.model.PreferenceRequest;
import com.example.preferences.model.PreferenceResponse;
import com.example.preferences.service.PreferenceService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/preferences")
public class PreferenceController {
    private final PreferenceService preferenceService;

    public PreferenceController(PreferenceService preferenceService) {
        this.preferenceService = preferenceService;
    }

    @GetMapping("/{customerId}")
    public PreferenceResponse getPreference(@PathVariable String customerId) {
        return preferenceService.getPreference(customerId);
    }

    @PutMapping("/{customerId}")
    public ResponseEntity<?> updatePreference(@PathVariable String customerId, @RequestBody PreferenceRequest request) {
        try {
            return ResponseEntity.ok(preferenceService.updatePreference(customerId, request.pollingIntervalSeconds()));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(ex.getMessage());
        }
    }
}
