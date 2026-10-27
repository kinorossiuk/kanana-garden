package dev.kinorossiuk.kananagarden.bridge;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class VehicleActionTest {
    private static final String VALID = "{\"action\":\"volume_up\",\"slots\":{},"
            + "\"confidence\":\"high\",\"requires_confirmation\":false}";

    @Test
    public void acceptsOneActionObject() {
        assertEquals("volume_up", VehicleAction.parse(VALID).action);
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsTrailingGarbage() {
        VehicleAction.parse(VALID + " trailing-garbage");
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsSecondObject() {
        VehicleAction.parse(VALID + VALID);
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsSingleQuotedJson() {
        VehicleAction.parse(VALID.replace("\"volume_up\"", "'volume_up'"));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsCommentInsideObject() {
        VehicleAction.parse(VALID.replace("\"slots\"", "// comment\n\"slots\""));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsPayloadOverLimitEvenWhenWhitespaceIsValidJson() {
        StringBuilder value = new StringBuilder(VALID);
        while (value.length() <= 4096) {
            value.append(' ');
        }
        VehicleAction.parse(value.toString());
    }
}
