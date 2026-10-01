[app]
title = MEGATRONIK
package.name = megatronik
package.domain = org.megatronik
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,mp3,wav
source.exclude_dirs = server, .github, bin, .buildozer
version = 1.1

requirements = python3,kivy==2.3.0,pillow,pyjnius,plyer,android,openssl,certifi

orientation = portrait
fullscreen = 1

android.permissions = CAMERA, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, INTERNET, ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1