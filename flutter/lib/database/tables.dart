import 'package:drift/drift.dart';

/// A telemetry sample captured while driving or walking.
class TripTelemetryLogs extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// Stored as epoch milliseconds for stable, timezone-independent sync.
  DateTimeColumn get timestamp => dateTime().named('timestamp')();

  RealColumn get latitude => real()();
  RealColumn get longitude => real()();
  RealColumn get currentSpeed => real()();
  RealColumn get accelerationDelta => real()();
  TextColumn get hazardType => text()();
  BoolColumn get isAnonymized =>
      boolean().withDefault(const Constant(true))();
}

/// A locally recorded blackbox event awaiting upload.
class BlackboxEvents extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// Stored as epoch milliseconds for stable, timezone-independent sync.
  DateTimeColumn get eventTimestamp => dateTime().named('event_timestamp')();

  RealColumn get locationLatitude =>
      real().named('location_latitude')();
  RealColumn get locationLongitude =>
      real().named('location_longitude')();
  TextColumn get localVideoPath => text()();
  BoolColumn get isProcessedLocalBlur =>
      boolean().named('is_processed_local_blur')();

  /// 0 = pending sync, 1 = successfully synced.
  IntColumn get syncStatus =>
      integer().named('sync_status').withDefault(const Constant(0))();
}
