# Ego Flutter local database

This module uses Drift with SQLCipher and stores the encryption key in
`flutter_secure_storage`. The database is opened with
`NativeDatabase.createInBackground`, so queries and writes run off the UI
isolate and can be used by a future background sync worker.

Generate Drift's typed implementation from this directory:

```bash
flutter pub get
dart run build_runner build --delete-conflicting-outputs
```

Keep `flutter/lib/database/database.g.dart` generated; do not edit it manually.

Run the local end-to-end vision/sync harness after generating Drift code:

```bash
dart run build_runner build --delete-conflicting-outputs
dart run bin/run_vision_sync_test.dart
```

The harness uses an in-memory database and temporary files, and removes its
temporary workspace when it exits.
