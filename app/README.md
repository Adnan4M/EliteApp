# Elite App (Flutter client)

Preparatory-year mobile client for the Elite AI Study Assistant. Talks to the
FastAPI backend in `../elite_bot` and shows **server-rendered highlighted page
images** — it ships no PDFs.

## Screens

- **Login / Register** — email + password; new accounts get a 7-day trial (first semester).
- **Profile** — subjects with progress bars, rank, tap a subject to update progress; semester toggle; subscription entry.
- **Search** — debounced autocomplete → results with four views: **المواضع** (page carousel, highlighted, prev/next), **ملخص**, **شرح** (simple/advanced/real-life/related), **أسئلة** (interactive MCQs + "Generate More").
- **Notifications** — announcements.
- **Support** — opens the support Telegram chat.
- **Subscription** — redeem a per-semester activation code.

Arabic-first, right-to-left, Material 3, light + dark.

## Prerequisites

- Flutter SDK 3.24+ (`flutter --version`). Not installed on the build machine yet —
  install from https://docs.flutter.dev/get-started/install
- The backend running and reachable (see `../elite_bot/README.md`):
  `uvicorn backend.main:app --app-dir elite_bot --host 0.0.0.0 --port 8000`

## Setup & run

This folder contains `lib/` and `pubspec.yaml`. Generate the platform shells and run:

```bash
cd app
flutter create .          # generates android/ ios/ etc. WITHOUT touching lib/ or pubspec
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:8000   # Android emulator -> host
```

- **Android emulator** reaches the host at `10.0.2.2` (the default in `lib/config.dart`).
- **iOS simulator / desktop**: use `--dart-define=API_BASE=http://localhost:8000`.
- **Physical device**: use your machine's LAN IP, e.g. `http://192.168.1.20:8000`.

### Android dev caveats

- Cleartext HTTP (dev backend) is blocked by default on Android 9+. For development,
  add `android:usesCleartextTraffic="true"` to `<application>` in
  `android/app/src/main/AndroidManifest.xml`. Use HTTPS in production.
- `url_launcher` on Android 11+ needs a `<queries>` entry for the Telegram/https intent
  in the manifest (see url_launcher docs).

## Structure

```
lib/
  main.dart              app root, RTL, auth-gated routing
  config.dart            API base URL, semesters
  models.dart            JSON models
  theme.dart             Material 3 theme (light/dark)
  api/
    api_client.dart      http + bearer token + typed ApiException (401/402/429)
    api.dart             typed endpoint methods
  state/
    auth_controller.dart token in secure storage; login/register/logout
  screens/
    login_screen.dart
    home_shell.dart      4-tab bottom nav + semester selector
    profile_tab.dart     progress + rank + update sheet
    search_tab.dart      autocomplete + search entry
    search_result_screen.dart   locations + summary + explanation + quiz
    page_viewer_screen.dart     highlighted page carousel (prev/next)
    notifications_tab.dart
    support_tab.dart
    subscription_screen.dart    redeem code
  widgets/common.dart    Loading / ErrorView / SectionCard
```

## Status

Written but **not yet compiled** — the build machine has no Flutter SDK. Once the SDK is
installed, run `flutter analyze` and fix any environment-specific lints before shipping.
