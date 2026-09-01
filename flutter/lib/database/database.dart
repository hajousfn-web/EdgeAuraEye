import 'dart:io';
import 'dart:math';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlcipher_flutter_libs/sqlcipher_flutter_libs.dart';

import 'tables.dart';

part 'database.g.dart';

const int pendingSync = 0;
const int successfullySynced = 1;

@DriftDatabase(tables: [TripTelemetryLogs, BlackboxEvents])
class EgoDatabase extends _$EgoDatabase {
  EgoDatabase(super.executor);

  @override
  int get schemaVersion => 1;

  Future<int> insertTelemetry(TripTelemetryLogsCompanion entry) =>
      into(tripTelemetryLogs).insert(entry);

  Future<int> insertBlackboxEvent(BlackboxEventsCompanion entry) =>
      into(blackboxEvents).insert(entry);

  Future<List<BlackboxEvent>> getPendingBlackboxEvents() {
    return (select(blackboxEvents)
          ..where((event) => event.syncStatus.equals(pendingSync))
          ..orderBy([(event) => OrderingTerm.asc(event.eventTimestamp)]))
        .get();
  }

  Stream<List<BlackboxEvent>> watchPendingBlackboxEvents() {
    return (select(blackboxEvents)
          ..where((event) => event.syncStatus.equals(pendingSync))
          ..orderBy([(event) => OrderingTerm.asc(event.eventTimestamp)]))
        .watch();
  }

  Future<void> markBlackboxEventSynced(int id) async {
    await (update(blackboxEvents)..where((event) => event.id.equals(id)))
        .write(const BlackboxEventsCompanion(
          syncStatus: Value(successfullySynced),
        ));
  }

  /// Keeps schema changes explicit and gives SQLite a durable WAL checkpoint.
  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (Migrator m) => m.createAll(),
        onUpgrade: (Migrator m, int from, int to) async {
          // Add versioned migrations here; never delete offline data silently.
        },
        beforeOpen: (details) async {
          await customStatement('PRAGMA foreign_keys = ON');
          await customStatement('PRAGMA journal_mode = WAL');
        },
      );
}

/// Application-facing name for the encrypted local database.
typedef EgoLocalDatabase = EgoDatabase;

/// Opens one encrypted database connection on a Drift worker isolate.
///
/// The key is generated once and kept in platform secure storage. It is never
/// persisted in the database or passed through application-level sync payloads.
Future<EgoDatabase> openEgoDatabase() async {
  await applyWorkaroundToOpenSqlite3OnOldAndroidVersions();

  const secureStorage = FlutterSecureStorage();
  var key = await secureStorage.read(key: 'ego_database_key');
  if (key == null || key.isEmpty) {
    key = _newDatabaseKey();
    await secureStorage.write(key: 'ego_database_key', value: key);
  }
  final databaseKey = key;

  final supportDirectory = await getApplicationSupportDirectory();
  final databaseFile = File(p.join(supportDirectory.path, 'ego.sqlite'));

  final executor = NativeDatabase.createInBackground(
    databaseFile,
    setup: (rawDatabase) {
      // SQLCipher accepts a quoted key and encrypts the complete SQLite file.
      final escapedKey = databaseKey.replaceAll("'", "''");
      rawDatabase.execute("PRAGMA key = '$escapedKey'");
      rawDatabase.execute('PRAGMA cipher_memory_security = ON');
    },
  );
  return EgoDatabase(executor);
}

String _newDatabaseKey() {
  final values = List<int>.generate(32, (_) => Random.secure().nextInt(256));
  return values.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
}
