plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.emco.multicamandroid"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.emco.multicamandroid"
        minSdk = 30
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

dependencies {
    // MultiCam Common Library
    implementation("com.multicam:multicam-common:1.1.0")

    implementation(libs.appcompat)
    implementation(libs.material)

    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.preview)
    implementation(libs.camerax.video)

    implementation(libs.gson)
    implementation(libs.jmdns)
    implementation(libs.aws.s3)
    implementation(libs.aws.mobile.client)

    testImplementation(libs.junit)
    androidTestImplementation(libs.ext.junit)
    androidTestImplementation(libs.espresso.core)
}