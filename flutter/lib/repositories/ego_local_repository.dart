import 'package:drift/drift.dart';

import '../database/database.dart';
import '../database/safe_database_operation.dart';

/// Application-facing boundary for all local persistence.
///
/// The repository only exposes domain values and generated read models. Drift
/// companions remain an implementation detail of this layer.
class EgoLocalRepository {
  EgoLocalRepository(
    this._database, {
    SafeDatabaseOperation? safeOperation,
  }) : _safeOperation = safeOperation ?? const SafeDatabaseOperation();

  final EgoDatabase _database;
  final SafeDatabaseOperation _safeOperation;

  Future<int> insertTelemetry({
    required DateTime timestamp,
    required double latitude,
    required double longitude,
    required double currentSpeed,
    required double accelerationDelta,
    required String hazardType,
    bool isAnonymized = true,
  }) {
    return _safeOperation.run<int>(
      operation: 'insertTelemetry',
      fallback: 0,
      action: () => _database.insertTelemetry(
        TripTelemetryLogsCompanion.insert(
          timestamp: timestamp,
          latitude: latitude,
          longitude: longitude,
          currentSpeed: currentSpeed,
          accelerationDelta: accelerationDelta,
          hazardType: hazardType,
          isAnonymized: Value(isAnonymized),
        ),
      ),
    );
  }

  Future<int> logBlackboxEvent({
    required DateTime eventTimestamp,
    required double latitude,
    required double longitude,
    required String localVideoPath,
    required bool isProcessedLocalBlur,
    int syncStatus = pendingSync,
  }) {
    return _safeOperation.run<int>(
      operation: 'logBlackboxEvent',
      fallback: 0,
      action: () => _database.insertBlackboxEvent(
        BlackboxEventsCompanion.insert(
          eventTimestamp: eventTimestamp,
          locationLatitude: latitude,
          locationLongitude: longitude,
          localVideoPath: localVideoPath,
          isProcessedLocalBlur: isProcessedLocalBlur,
          syncStatus: Value(syncStatus),
        ),
      ),
    );
  }

  Future<List<BlackboxEvent>> fetchPendingBlackboxEvents() {
    return _safeOperation.run<List<BlackboxEvent>>(
      operation: 'fetchPendingBlackboxEvents',
      fallback: const <BlackboxEvent>[],
      action: _database.getPendingBlackboxEvents,
    );
  }

  Stream<List<BlackboxEvent>> watchPendingBlackboxEvents() {
    return _watchPendingBlackboxEventsSafely();
  }

  Stream<List<BlackboxEvent>> _watchPendingBlackboxEventsSafely() async* {
    try {
      yield* _database.watchPendingBlackboxEvents();
    } on Exception catch (error, stackTrace) {
      _safeOperation.report('watchPendingBlackboxEvents', error, stackTrace);
      yield const <BlackboxEvent>[];
    }
  }

  Future<bool> markBlackboxEventSynced(int id) {
    return _safeOperation.run<bool>(
      operation: 'markBlackboxEventSynced',
      fallback: false,
      action: () async {
        await _database.markBlackboxEventSynced(id);
        return true;
      },
    );
  }

}
