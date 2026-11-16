# Android foreground notification channel

In the pinned upstream, `MainService.initNotification` created an ID of `RustDesk`, named it `RustDesk Service` and described it as `RustDesk Service Channel`. The merchant language patch later localized the visible name and description in English, Simplified Chinese and Spanish. It retained the original ID and both support-edition RustDesk fallbacks. The foreground notification dump prints the ID in `Notification(channel=…)`. Android Settings displays the name. [Upstream MainService](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainService.kt#L816-L841) · [Previous merchant language patch](../../patches/0029-merchant-languages.patch)

| Installation | Foreground dump, Android 8+ | Settings in English / 简体中文 / Español |
| --- | --- | --- |
| Fresh, on first service use | `channel=SteadDesk` | SteadDesk service / SteadDesk 服务 / Servicio de SteadDesk |
| Upgrade with the original channel | `channel=RustDesk` | SteadDesk service / SteadDesk 服务 / Servicio de SteadDesk |

The package-replacement broadcast updates the existing channel in place, including when the service is paused. If Android defers the broadcast, opening the app or initializing the service also refreshes the name. System locale changes refresh the channel, and saving the merchant language refreshes it immediately. A merchant language override takes precedence over the system locale. The first service use creates a channel when one does not yet exist.

Android persists notification behavior against the channel ID. Updating only the name and description preserves the user's sound, vibration, importance, private/lock-screen settings and notification block. All service notifications use the channel returned by the same builder factory. Repeated metadata refreshes do not post notifications. [Android channel behavior](https://developer.android.com/develop/ui/compose/notifications/channels)

## Verification

`python3 -B -m unittest discover -s scripts/tests -p test_service_notification_channel.py -v` runs the production receiver, channel/builder selection and merchant locale code against host Android API fixtures, using the actual shared XML translations. The eight cases cover a fresh install, muted/blocked upgrades, repeated updates, conflicting historical IDs with a block, denied app notifications, support locale changes and pre-Android-8 behavior.

Both edition-specific Kotlin/Java service and activity paths were compiled locally against Android API 36. Device notification delivery, Android Settings and OEM broadcast timing require device validation.
