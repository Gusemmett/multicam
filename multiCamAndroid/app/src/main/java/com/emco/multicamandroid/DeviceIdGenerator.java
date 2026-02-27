package com.emco.multicamandroid;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import java.util.Arrays;
import java.util.List;
import java.util.Random;
import java.util.UUID;

public class DeviceIdGenerator {
    private static final String TAG = "DeviceIdGenerator";
    private static final String PREFS_NAME = "MultiCamPrefs";
    private static final String DEVICE_ID_KEY = "device_id";

    private static final List<String> NOUNS = Arrays.asList(
        "Valley", "Mountain", "River", "Ocean", "Forest", "Desert", "Island", "Canyon",
        "Meadow", "Prairie", "Glacier", "Volcano", "Beach", "Lake", "Stream", "Ridge",
        "Peak", "Grove", "Field", "Marsh", "Cliff", "Cove", "Bay", "Pond",
        "Hill", "Plains", "Falls", "Spring", "Creek", "Woods", "Dune", "Reef",
        "Harbor", "Fjord", "Valley", "Oasis", "Cavern", "Plateau", "Delta", "Gorge",
        "Summit", "Cascade", "Bluff", "Lagoon", "Rapids", "Glade", "Thicket", "Hollow",
        "Orchard", "Vineyard", "Garden", "Pasture", "Barnyard", "Farmland", "Countryside", "Village",
        "Town", "City", "Castle", "Tower", "Bridge", "Road", "Path", "Trail",
        "Avenue", "Square", "Plaza", "Market", "Park", "Garden", "Fountain", "Monument",
        "Library", "Museum", "Theater", "Gallery", "Studio", "Workshop", "Factory", "Mill",
        "Forge", "Kiln", "Oven", "Kitchen", "Pantry", "Cellar", "Attic", "Loft",
        "Cabin", "Cottage", "Manor", "Palace", "Temple", "Chapel", "Cathedral", "Shrine",
        "Observatory", "Laboratory", "Greenhouse", "Conservatory", "Aviary", "Aquarium", "Zoo", "Safari"
    );

    public static String getDeviceId(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String existingId = prefs.getString(DEVICE_ID_KEY, null);

        if (existingId != null) {
            Log.d(TAG, "Using existing device ID: " + existingId);
            return existingId;
        }

        // Generate new device ID
        String newId = generateNewDeviceId();

        // Save it to preferences
        SharedPreferences.Editor editor = prefs.edit();
        editor.putString(DEVICE_ID_KEY, newId);
        editor.apply();

        Log.i(TAG, "Generated new device ID: " + newId);
        return newId;
    }

    private static String generateNewDeviceId() {
        Random random = new Random();

        // Select a random noun
        String noun = NOUNS.get(random.nextInt(NOUNS.size()));

        // Generate UUID and take first 8 characters
        String uuid = UUID.randomUUID().toString().toUpperCase();
        String uuidPart = uuid.substring(0, 8);

        // Combine noun and UUID part
        String deviceId = noun + "-" + uuidPart;

        Log.d(TAG, "Generated device ID components: noun=" + noun + ", uuid=" + uuidPart);

        return deviceId;
    }

    // Method to regenerate device ID (for testing or reset purposes)
    public static String regenerateDeviceId(Context context) {
        String newId = generateNewDeviceId();

        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        SharedPreferences.Editor editor = prefs.edit();
        editor.putString(DEVICE_ID_KEY, newId);
        editor.apply();

        Log.i(TAG, "Regenerated device ID: " + newId);
        return newId;
    }
}