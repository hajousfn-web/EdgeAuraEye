import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:path/path.dart' as p;

import '../database/database.dart';
import '../database/safe_database_operation.dart';
import '../services/ego_telemetry_service.dart';

/// A local camera or video frame as it enters the device-side vision pipeline.
class VisionFrame {
  const VisionFrame({
    required this.captureAt,
    required this.filePath,
    required this.width,
    required this.height,
    required this.deviceId,
    this.metadata = const <String, Object>{},
  });

  final DateTime captureAt;
  final String filePath;
  final int width;
  final int height;
  final String deviceId;
  final Map<String, Object> metadata;
}

/// Snapshot of the current local driving telemetry used to decide if a hazard
/// trigger should be raised.
class TelemetrySnapshot {
  const TelemetrySnapshot({
    required this.timestamp,
    required this.latitude,
    required this.longitude,
    required this.currentSpeed,
    required this.accelerationDelta,
    required this.hazardType,
  });

  final DateTime timestamp;
  final double latitude;
  final double longitude;
  final double currentSpeed;
  final double accelerationDelta;
  final String hazardType;
}

/// Adapter contract for camera or video frame ingestion. Implementations may be
/// backed by OpenCV, Camera2, AVFoundation, or a local test source.
abstract interface class LocalFrameSource {
  Stream<VisionFrame> get frameStream;
}

/// Describes whether a given frame should trigger a local hazard capture.
abstract interface class HazardDetector {
  bool shouldTrigger(VisionFrame frame, TelemetrySnapshot telemetry);
}

/// Default detector for edge events based on sudden acceleration delta.
class AccelerationDeltaHazardDetector implements HazardDetector {
  const AccelerationDeltaHazardDetector({this.threshold = 2.5});

  final double threshold;

  @override
  bool shouldTrigger(VisionFrame frame, TelemetrySnapshot telemetry) {
    final delta = telemetry.accelerationDelta.abs();
    return delta >= threshold;
  }
}

/// Local capture loop responsible for persisting the critical event clip and
/// storing the metadata in the encrypted local database.
class LocalHazardCaptureLoop {
  LocalHazardCaptureLoop({
    required EgoTelemetryService telemetryService,
    required String captureDirectory,
    SafeDatabaseOperation? safeOperation,
  })  : _telemetryService = telemetryService,
        _captureDirectory = captureDirectory,
        _safeOperation = safeOperation ?? const SafeDatabaseOperation();

  final EgoTelemetryService _telemetryService;
  final String _captureDirectory;
  final SafeDatabaseOperation _safeOperation;

  Future<String?> captureCriticalEvent({
    required VisionFrame triggerFrame,
    required TelemetrySnapshot telemetry,
    required String reason,
  }) async {
    return _safeOperation.run<String?>(
      operation: 'captureCriticalEvent',
      fallback: null,
      action: () async {
        final rootDirectory = Directory(_captureDirectory);
        await rootDirectory.create(recursive: true);

        final eventStamp = triggerFrame.captureAt.millisecondsSinceEpoch;
        final eventFolder = Directory(p.join(_captureDirectory, 'event_$eventStamp'));
        await eventFolder.create(recursive: true);

        final sourceFile = File(triggerFrame.filePath);
        final targetPath = p.join(
          eventFolder.path,
          'clip_${eventStamp}_$reason.mp4',
        );

        if (await sourceFile.exists()) {
          await sourceFile.copy(targetPath);
        } else {
          final placeholder = File(targetPath);
          await placeholder.writeAsBytes(const <int>[], flush: true);
        }

        final telemetryInsertId = await _telemetryService.insertTelemetryRecord(
          timestamp: telemetry.timestamp,
          latitude: telemetry.latitude,
          longitude: telemetry.longitude,
          currentSpeed: telemetry.currentSpeed,
          accelerationDelta: telemetry.accelerationDelta,
          hazardType: telemetry.hazardType,
          isAnonymized: true,
        );

        if (telemetryInsertId == 0) {
          return null;
        }

        final blackboxInsertId = await _telemetryService.insertBlackboxEventRecord(
          eventTimestamp: triggerFrame.captureAt,
          latitude: telemetry.latitude,
          longitude: telemetry.longitude,
          localVideoPath: targetPath,
          isProcessedLocalBlur: true,
          syncStatus: pendingSync,
        );

        if (blackboxInsertId == 0) {
          return null;
        }

        final metadataFile = File(p.join(eventFolder.path, 'event_meta.json'));
        final metadata = <String, Object>{
          'id': blackboxInsertId,
          'eventTimestamp': triggerFrame.captureAt.toIso8601String(),
          'latitude': telemetry.latitude,
          'longitude': telemetry.longitude,
          'currentSpeed': telemetry.currentSpeed,
          'accelerationDelta': telemetry.accelerationDelta,
          'hazardType': telemetry.hazardType,
          'reason': reason,
          'videoPath': targetPath,
          'deviceId': triggerFrame.deviceId,
        };
        await metadataFile.writeAsString(
          const JsonEncoder.withIndent('  ').convert(metadata),
          flush: true,
        );

        return targetPath;
      },
    );
  }
}

/// Real-time local vision & hazard capture coordinator.
///
/// This loop remains fully local: it observes camera frames, evaluates hazard
/// conditions against the current telemetry state, and persists the event to the
/// encrypted local Drift database without any cloud or remote dependencies.
class EgoHazardCaptureEngine {
  EgoHazardCaptureEngine({
    required LocalFrameSource frameSource,
    required EgoTelemetryService telemetryService,
    required LocalHazardCaptureLoop captureLoop,
    HazardDetector? hazardDetector,
    SafeDatabaseOperation? safeOperation,
    this.minCaptureInterval = const Duration(seconds: 5),
    void Function(Object error, StackTrace stackTrace)? onError,
  })  : _frameSource = frameSource,
        _telemetryService = telemetryService,
        _captureLoop = captureLoop,
        _hazardDetector = hazardDetector ?? const AccelerationDeltaHazardDetector(),
        _safeOperation = safeOperation ?? const SafeDatabaseOperation(),
        _onError = onError ?? _defaultErrorHandler;

  final LocalFrameSource _frameSource;
  final EgoTelemetryService _telemetryService;
  final LocalHazardCaptureLoop _captureLoop;
  final HazardDetector _hazardDetector;
  final SafeDatabaseOperation _safeOperation;
  final Duration minCaptureInterval;
  final void Function(Object error, StackTrace stackTrace) _onError;

  StreamSubscription<VisionFrame>? _subscription;
  TelemetrySnapshot? _latestTelemetry;
  DateTime? _lastCaptureAt;
  bool _captureInProgress = false;

  void updateTelemetry(TelemetrySnapshot snapshot) {
    _latestTelemetry = snapshot;
  }

  Future<void> start() async {
    await stop();
    _subscription = _frameSource.frameStream.listen(
      (frame) {
        unawaited(_onFrame(frame));
      },
      onError: (Object error, StackTrace stackTrace) {
        _safeOperation.report('vision_loop', error, stackTrace);
      },
    );
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
  }

  Future<void> _onFrame(VisionFrame frame) async {
    final telemetry = _latestTelemetry;
    if (telemetry == null) {
      return;
    }

    if (!_hazardDetector.shouldTrigger(frame, telemetry)) {
      return;
    }

    final now = DateTime.now();
    final last = _lastCaptureAt;
    if (last != null && now.difference(last) < minCaptureInterval) {
      return;
    }

    if (_captureInProgress) {
      return;
    }

    _captureInProgress = true;
    try {
      _lastCaptureAt = now;
      await _captureLoop.captureCriticalEvent(
        triggerFrame: frame,
        telemetry: telemetry,
        reason: 'acceleration_delta',
      );
    } on Exception catch (error, stackTrace) {
      _onError(error, stackTrace);
    } finally {
      _captureInProgress = false;
    }
  }

  static void _defaultErrorHandler(Object error, StackTrace stackTrace) {
    developer.log(
      'Local vision capture failed',
      name: 'ego.vision',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
