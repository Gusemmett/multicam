package com.multicam.common;

import com.google.gson.annotations.SerializedName;

/**
 * Device type values used in API responses.
 */
public enum DeviceType {
    /** iOS device (iPhone) */
    @SerializedName("iOS:iPhone")
    IOS_IPHONE("iOS:iPhone"),

    /** Android phone device */
    @SerializedName("Android:Phone")
    ANDROID_PHONE("Android:Phone"),

    /** Android Quest VR headset */
    @SerializedName("Android:Quest")
    ANDROID_QUEST("Android:Quest"),

    /** OAK camera device */
    @SerializedName("Oak")
    OAK("Oak");

    private final String value;

    DeviceType(String value) {
        this.value = value;
    }

    /**
     * Get the string value of this device type.
     *
     * @return Device type string value
     */
    public String getValue() {
        return value;
    }

    /**
     * Get DeviceType from string value.
     *
     * @param value Device type string value
     * @return DeviceType enum value, or null if not found
     */
    public static DeviceType fromValue(String value) {
        for (DeviceType type : values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        return null;
    }
}
