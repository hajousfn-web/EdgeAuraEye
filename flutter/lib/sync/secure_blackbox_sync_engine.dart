import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';

import '../database/database.dart';
import '../services/ego_telemetry_service.dart';

/// Local network reachability contract used by the background sync worker.
abstract interface class SyncNetworkStatus {
  Future<bool> isOnline();
}

/// Auth token provider for secure sync transport.
abstract interface class SyncAuthProvider {
  Future<String?> getAccessToken();
}

/// Immutable payload structure for a single local blackbox record.
class BlackboxSyncPayload {
  const BlackboxSyncPayload({
    required this.id,
    required this.eventTimestamp,
    required this.latitude,
    required this.longitude,
    required this.localVideoPath,
    required this.syncStatus,
    required this.idempotencyKey,
    required this.recordedAt,
  });

  final int id;
  final DateTime eventTimestamp;
  final double latitude;
  final double longitude;
  final String localVideoPath;
  final int syncStatus;
  final String idempotencyKey;
  final DateTime recordedAt;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'id': id,
      'eventTimestamp': eventTimestamp.toUtc().toIso8601String(),
      'latitude': latitude,
      'longitude': longitude,
      'localVideoPath': localVideoPath,
      'syncStatus': syncStatus,
      'idempotencyKey': idempotencyKey,
      'recordedAt': recordedAt.toUtc().toIso8601String(),
    };
  }
}

/// Local transport contract used by the sync engine.
abstract interface class SecureSyncTransport {
  Future<HttpClientResponse> sendBatch({
    required String authToken,
    required List<BlackboxSyncPayload> payload,
    required Uri endpoint,
  });
}

/// Default implementation using an authenticated HTTP client.
class HttpSecureSyncTransport implements SecureSyncTransport {
  HttpSecureSyncTransport({
    this.client,
    this.defaultHeaders = const <String, String>{},
  });

  final HttpClient? client;
  final Map<String, String> defaultHeaders;

  @override
  Future<HttpClientResponse> sendBatch({
    required String authToken,
    required List<BlackboxSyncPayload> payload,
    required Uri endpoint,
  }) async {
    final httpClient = client ?? HttpClient();
    final request = await httpClient.postUrl(endpoint);
    request.headers.set('Authorization', 'Bearer $authToken');
    request.headers.set('Content-Type', 'application/json');
    request.headers.set('Accept', 'application/json');
    for (final entry in defaultHeaders.entries) {
      request.headers.set(entry.key, entry.value);
    }

    final body = jsonEncode({
      'items': payload.map((item) => item.toJson()).toList(),
      'batchCount': payload.length,
      'sentAt': DateTime.now().toUtc().toIso8601String(),
    });

    request.write(body);
    return request.close();
  }
}

/// Retry/backoff strategy intentionally local and safe.
class SyncRetryPolicy {
  const SyncRetryPolicy({
    this.maxAttempts = 4,
    this.baseDelay = const Duration(seconds: 2),
    this.maxDelay = const Duration(minutes: 2),
    this.jitter = 0.2,
  });

  final int maxAttempts;
  final Duration baseDelay;
  final Duration maxDelay;
  final double jitter;

  Duration delayForAttempt(int attempt) {
    final exponent = attempt - 1;
    final raw = baseDelay.inMilliseconds * (1 << exponent);
    final capped = raw > maxDelay.inMilliseconds ? maxDelay.inMilliseconds : raw;
    final jittered = capped * (1 + (jitter * (DateTime.now().microsecondsSinceEpoch % 1000) / 1000));
    return Duration(milliseconds: jittered.round());
  }
}

/// Batches local records for efficient upload while preserving a full local copy
/// until a confirmed acknowledgement is received.
class BlackboxSyncBatch {
  const BlackboxSyncBatch({required this.items});

  final List<BlackboxSyncPayload> items;

  bool get isEmpty => items.isEmpty;

  int get size => items.length;
}

/// Worker responsible for fetching pending blackbox rows, batching them, and
/// attempting secure transmission without compromising the local encrypted copy.
class SecureBlackboxSyncEngine {
  SecureBlackboxSyncEngine({
    required EgoTelemetryService telemetryService,
    required SyncNetworkStatus networkStatus,
    required SyncAuthProvider authProvider,
    required Uri endpoint,
    SecureSyncTransport? transport,
    SyncRetryPolicy retryPolicy = const SyncRetryPolicy(),
    Duration interval = const Duration(minutes: 5),
    void Function(Object error, StackTrace stackTrace)? onError,
  })  : _telemetryService = telemetryService,
        _networkStatus = networkStatus,
        _authProvider = authProvider,
        _endpoint = endpoint,
        _transport = transport ?? HttpSecureSyncTransport(),
        _retryPolicy = retryPolicy,
        _interval = interval,
        _onError = onError ?? _defaultErrorHandler;

  final EgoTelemetryService _telemetryService;
  final SyncNetworkStatus _networkStatus;
  final SyncAuthProvider _authProvider;
  final Uri _endpoint;
  final SecureSyncTransport _transport;
  final SyncRetryPolicy _retryPolicy;
  final Duration _interval;
  final void Function(Object error, StackTrace stackTrace) _onError;

  Timer? _timer;
  bool _syncInProgress = false;

  void start() {
    _timer ??= Timer.periodic(_interval, (_) => unawaited(runOnce()));
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> runOnce() async {
    if (_syncInProgress) {
      return;
    }
    _syncInProgress = true;

    try {
      if (!await _networkStatus.isOnline()) {
        return;
      }

      final pending = await _telemetryService.getPendingBlackboxEvents();
      if (pending.isEmpty) {
        return;
      }

      final batch = _buildBatch(pending);
      if (batch.isEmpty) {
        return;
      }

      final token = await _authProvider.getAccessToken();
      if (token == null || token.isEmpty) {
        developer.log(
          'Sync skipped: missing auth token',
          name: 'ego.sync',
        );
        return;
      }

      final response = await _sendWithRetry(
        authToken: token,
        payload: batch.items,
      );

      if (response.statusCode >= 200 && response.statusCode < 300) {
        for (final item in batch.items) {
          await _telemetryService.markBlackboxEventSynced(item.id);
        }
      }
    } on Exception catch (error, StackTrace stackTrace) {
      _onError(error, stackTrace);
    } finally {
      _syncInProgress = false;
    }
  }

  BlackboxSyncBatch _buildBatch(List<BlackboxEvent> pending) {
    final items = <BlackboxSyncPayload>[];
    for (final event in pending) {
      items.add(
        BlackboxSyncPayload(
          id: event.id,
          eventTimestamp: event.eventTimestamp,
          latitude: event.locationLatitude,
          longitude: event.locationLongitude,
          localVideoPath: event.localVideoPath,
          syncStatus: event.syncStatus,
          idempotencyKey: 'blackbox:${event.id}',
          recordedAt: DateTime.now(),
        ),
      );
    }
    return BlackboxSyncBatch(items: items);
  }

  Future<HttpClientResponse> _sendWithRetry({
    required String authToken,
    required List<BlackboxSyncPayload> payload,
  }) async {
    HttpClientResponse? lastResponse;

    for (var attempt = 1; attempt <= _retryPolicy.maxAttempts; attempt++) {
      try {
        final response = await _transport.sendBatch(
          authToken: authToken,
          payload: payload,
          endpoint: _endpoint,
        );
        lastResponse = response;

        if (response.statusCode >= 200 && response.statusCode < 300) {
          return response;
        }

        if (attempt < _retryPolicy.maxAttempts) {
          await Future<void>.delayed(_retryPolicy.delayForAttempt(attempt));
        }
      } on Exception catch (error, stackTrace) {
        _onError(error, stackTrace);
        if (attempt >= _retryPolicy.maxAttempts) {
          rethrow;
        }
        await Future<void>.delayed(_retryPolicy.delayForAttempt(attempt));
      }
    }

    if (lastResponse != null) {
      return lastResponse;
    }

    throw const HttpException('Blackbox sync retry loop failed without a response.');
  }

  static void _defaultErrorHandler(Object error, StackTrace stackTrace) {
    developer.log(
      'Secure blackbox sync failed',
      name: 'ego.sync',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
