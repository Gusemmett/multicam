# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Android application project called "multiCamAndroid" with package name `com.emco.multicamandroid`. It appears to be a new/skeleton Android project set up with standard Android Gradle build system.

## Build System & Commands

### Building the Project
```bash
./gradlew build                 # Build the entire project
./gradlew assembleDebug         # Build debug APK
./gradlew assembleRelease       # Build release APK
./gradlew installDebug          # Install debug build to connected device
```

### Testing
```bash
./gradlew test                  # Run unit tests
./gradlew connectedAndroidTest  # Run instrumented tests (requires device/emulator)
./gradlew testDebugUnitTest     # Run unit tests for debug variant
```

### Development
```bash
./gradlew clean                 # Clean build artifacts
./gradlew lint                  # Run Android lint checks
./gradlew lintDebug            # Run lint for debug variant
```

## Project Structure

- **Root build.gradle.kts**: Top-level build configuration using version catalog
- **app/build.gradle.kts**: Main app module configuration
- **gradle/libs.versions.toml**: Version catalog for dependency management
- **settings.gradle.kts**: Project settings and module configuration

### Key Configuration Details

- **Target SDK**: 34 (Android 14)
- **Min SDK**: 30 (Android 11)
- **Compile SDK**: 34
- **Java Version**: 11
- **Package**: `com.emco.multicamandroid`
- **App Name**: "multiCamAndroid"

### Dependencies

The project uses standard Android dependencies managed through version catalog:
- AndroidX AppCompat
- Material Design Components
- JUnit for unit testing
- Espresso for UI testing

### Source Structure

- **app/src/main/java/com/emco/multicamandroid/**: Main application source code (currently empty)
- **app/src/test/**: Unit tests
- **app/src/androidTest/**: Instrumented tests
- **app/src/main/res/**: Android resources (layouts, strings, drawables, etc.)
- **app/src/main/AndroidManifest.xml**: App manifest

### Build Configuration

- Uses Kotlin DSL for Gradle files (.gradle.kts)
- Version catalog pattern for dependency management
- Standard Android build types (debug/release)
- ProGuard disabled for release builds
- AndroidX and non-transitive R classes enabled

## Development Notes

This appears to be a freshly initialized Android project with no custom source code yet. The main package directory exists but contains no Java/Kotlin files. When adding new features, follow standard Android architecture patterns and place source files in the appropriate package structure under `app/src/main/java/com/emco/multicamandroid/`.