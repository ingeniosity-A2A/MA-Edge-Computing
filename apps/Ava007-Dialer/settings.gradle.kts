pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Telnyx publishes the WebRTC Android SDK through JitPack.
        maven("https://jitpack.io")
    }
}

rootProject.name = "Ava007Dialer"
include(":app")
