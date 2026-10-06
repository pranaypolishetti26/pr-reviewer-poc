package com.example.preferences.controller;

import com.example.preferences.CustomerPreferencesApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = CustomerPreferencesApplication.class)
@AutoConfigureMockMvc
class PreferenceControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void rejectsInvalidPollingInterval() throws Exception {
        mockMvc.perform(put("/api/preferences/customer-1")
                .contentType("application/json")
                .content("{\"pollingIntervalSeconds\":10}"))
                .andExpect(status().isBadRequest());
    }
}
