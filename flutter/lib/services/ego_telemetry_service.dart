import 'package:drift/drift.dart';

import '../database/database.dart';
import '../database/safe_database_operation.dart';

/// Local-only telemetry and blackbox persistence service for the Ego app.
///
/// This service is the boundary between application logic and the encrypted
/// Drift database. It intentionally contains no cloud, sync, or network code.
class EgoTelemetryService {
  EgoTelemetryService({
    required EgoDatabase database,
    SafeDatabaseOperation? safeOperation,
  })  : _database = database,
        _safeOperation = safeOperation ?? const SafeDatabaseOperation();

  final EgoDatabase _database;
  final SafeDatabaseOperation _safeOperation;

  Future<int> insertTelemetry(TripTelemetryLogsCompanion entry) {
    return _safeOperation.run<int>(
      operation: 'insertTelemetry',
      fallback: 0,
      action: () => _database.insertTelemetry(entry),
    );
  }

  Future<int> insertTelemetryRecord({
    required DateTime timestamp,
    required double latitude,
    required double longitude,
    required double currentSpeed,
    required double accelerationDelta,
    required String hazardType,
    bool isAnonymized = true,
  }) {
    return insertTelemetry(
      TripTelemetryLogsCompanion.insert(
        timestamp: timestamp,
        latitude: latitude,
        longitude: longitude,
        currentSpeed: currentSpeed,
        accelerationDelta: accelerationDelta,
        hazardType: hazardType,
        isAnonymized: Value(isAnonymized),
      ),
    );
  }

  Future<int> insertBlackboxEvent(BlackboxEventsCompanion entry) {
    return _safeOperation.run<int>(
      operation: 'insertBlackboxEvent',
      fallback: 0,
      action: () => _database.insertBlackboxEvent(entry),
    );
  }

  Future<int> insertBlackboxEventRecord({
    required DateTime eventTimestamp,
    required double latitude,
    required double longitude,
    required String localVideoPath,
    required bool isProcessedLocalBlur,
    int syncStatus = pendingSync,
  }) {
    return insertBlackboxEvent(
      BlackboxEventsCompanion.insert(
        eventTimestamp: eventTimestamp,
        locationLatitude: latitude,
        locationLongitude: longitude,
        localVideoPath: localVideoPath,
        isProcessedLocalBlur: isProcessedLocalBlur,
        syncStatus: Value(syncStatus),
      ),
    );
  }

  Future<List<BlackboxEvent>> getPendingBlackboxEvents() {
    return _safeOperation.run<List<BlackboxEvent>>(
      operation: 'getPendingBlackboxEvents',
      fallback: const <BlackboxEvent>[],
      action: _database.getPendingBlackboxEvents,
    );
  }

  Stream<List<BlackboxEvent>> watchPendingBlackboxEvents() {
    return _database.watchPendingBlackboxEvents().handleError(
      (Object error, StackTrace stackTrace) {
        _safeOperation.report('watchPendingBlackboxEvents', error, stackTrace);
      },
      test: (error) => error is Exception,
    );
  }

  Future<void> markBlackboxEventSynced(int id) {
    return _safeOperation.run<void>(
      operation: 'markBlackboxEventSynced',
      fallback: null,
      action: () async {
        await _database.markBlackboxEventSynced(id);
      },
    );
  }
}
