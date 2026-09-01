import 'dart:async';
import 'dart:developer' as developer;

import '../database/database.dart';
import '../repositories/ego_local_repository.dart';

abstract interface class NetworkStatus {
  Future<bool> isOnline();
}

/// Transport contract. It receives only anonymized paths and metadata.
abstract interface class AnonymizedSyncTransport {
  Future<bool> sendBlackboxEvent(AnonymizedBlackboxPayload payload);
}

class AnonymizedBlackboxPayload {
  const AnonymizedBlackboxPayload({
    required this.id,
    required this.eventTimestamp,
    required this.latitude,
    required this.longitude,
    required this.anonymizedVideoPath,
    required this.idempotencyKey,
  });

  final int id;
  final DateTime eventTimestamp;
  final double latitude;
  final double longitude;
  final String anonymizedVideoPath;
  final String idempotencyKey;
}

/// UI-independent coordinator for periodic, retryable offline synchronization.
class EgoVisionAndSyncEngine {
  EgoVisionAndSyncEngine({
    required EgoLocalRepository repository,
    required NetworkStatus networkStatus,
    required AnonymizedSyncTransport transport,
    Duration interval = const Duration(minutes: 15),
    void Function(Object error, StackTrace stackTrace)? onError,
  })  : _repository = repository,
        _networkStatus = networkStatus,
        _transport = transport,
        _interval = interval,
        _onError = onError ?? _defaultErrorHandler;

  final EgoLocalRepository _repository;
  final NetworkStatus _networkStatus;
  final AnonymizedSyncTransport _transport;
  final Duration _interval;
  final void Function(Object error, StackTrace stackTrace) _onError;
  Timer? _timer;
  bool _syncInProgress = false;

  /// Executes one bounded sync pass; safe to call from WorkManager/BGTask.
  Future<void> runOnce() async {
    if (_syncInProgress) return;
    _syncInProgress = true;
    try {
      if (!await _networkStatus.isOnline()) return;
      final pending = await _repository.fetchPendingBlackboxEvents();
      for (final event in pending) {
        try {
          final sent = await _transport.sendBlackboxEvent(
            AnonymizedBlackboxPayload(
              id: event.id,
              eventTimestamp: event.eventTimestamp,
              latitude: event.locationLatitude,
              longitude: event.locationLongitude,
              anonymizedVideoPath: event.localVideoPath,
              idempotencyKey: 'blackbox:${event.id}',
            ),
          );
          if (sent) {
            await _repository.markBlackboxEventSynced(event.id);
          }
        } on Exception catch (error, stackTrace) {
          _onError(error, stackTrace);
          // Keep this record pending and continue with the remaining queue.
        }
      }
    } on Exception catch (error, stackTrace) {
      _onError(error, stackTrace);
    } finally {
      _syncInProgress = false;
    }
  }

  void start() {
    _timer ??= Timer.periodic(_interval, (_) {
      unawaited(runOnce());
    });
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> dispose() async {
    stop();
  }

  static void _defaultErrorHandler(Object error, StackTrace stackTrace) {
    developer.log(
      'Background synchronization failed',
      name: 'ego.sync',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
