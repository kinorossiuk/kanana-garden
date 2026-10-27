package dev.kinorossiuk.kananagarden.bridge;

import static org.junit.Assert.assertFalse;

import org.junit.Test;

public class SecretRedactorTest {
    @Test
    public void redactsBearerAssignmentsAndCommonSecrets() {
        String[] inputs = {
                "Authorization: Bearer very-secret-token",
                "Authorization:Bearer very-secret-token",
                "Bearer very-secret-token",
                "token=very-secret-token",
                "password: very-secret-token"
        };
        for (String input : inputs) {
            String output = SecretRedactor.redact(input);
            assertFalse(input, output.contains("very-secret-token"));
        }
    }
}
