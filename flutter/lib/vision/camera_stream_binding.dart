import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

import '../performance/edge_performance_monitor.dart';
import 'ego_hazard_capture_engine.dart' as hazard;

/// A raw camera sample produced by a source. This is intentionally local-only and
/// does not carry any cloud identifiers or network metadata.
class CameraFrameSample {
  const CameraFrameSample({
    required this.timestamp,
    required this.width,
    required this.height,
    required this.source,
    required this.payload,
    this.metadata = const <String, Object>{},
  });

  final DateTime timestamp;
  final int width;
  final int height;
  final String source;
  final Uint8List payload;
  final Map<String, Object> metadata;
}

/// Structured local frame contract used by the offline vision pipeline.
class VisionFrame {
  const VisionFrame({
    required this.frameId,
    required this.timestamp,
    required this.width,
    required this.height,
    required this.source,
    required this.payload,
    this.metadata = const <String, Object>{},
  });

  final int frameId;
  final DateTime timestamp;
  final int width;
  final int height;
  final String source;
  final Uint8List payload;
  final Map<String, Object> metadata;
}

/// Abstract source of camera or video frames. Implementations may be file-based,
/// hardware-bound, or a deterministic test harness.
abstract interface class CameraSource {
  Stream<CameraFrameSample> get frames;

  Future<void> start();
  Future<void> stop();
}

/// Deterministic testing source that replays a local video or image file as a
/// stream of synthetic camera samples. This is safe for local tests and CI.
class VideoFileSource implements CameraSource {
  VideoFileSource({
    required String filePath,
    required this.frameInterval,
    this.frameWidth = 1280,
    this.frameHeight = 720,
    this.sourceId = 'video-file',
    this.onError,
  })  : _filePath = filePath,
        _payload = File(filePath).readAsBytesSync();

  final String _filePath;
  final Duration frameInterval;
  final int frameWidth;
  final int frameHeight;
  final String sourceId;
  final void Function(Object error, StackTrace stackTrace)? onError;
  final Uint8List _payload;
  StreamSubscription<CameraFrameSample>? _subscription;
  final StreamController<CameraFrameSample> _controller =
      StreamController<CameraFrameSample>.broadcast();

  @override
  Stream<CameraFrameSample> get frames => _controller.stream;

  @override
  Future<void> start() async {
    await stop();

    final timer = Timer.periodic(frameInterval, (tick) {
      final sample = CameraFrameSample(
        timestamp: DateTime.now(),
        width: frameWidth,
        height: frameHeight,
        source: sourceId,
        payload: Uint8List.fromList(_payload),
        metadata: {
          'filePath': _filePath,
          'frameIndex': tick,
        },
      );
      if (!_controller.isClosed) {
        _controller.add(sample);
      }
    });

    _subscription = timer.asStream().listen((_) {}, onError: (Object error, StackTrace stackTrace) {
      onError?.call(error, stackTrace);
    });
  }

  @override
  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
    if (!_controller.isClosed) {
      await _controller.close();
    }
  }
}

/// Real hardware camera abstraction. In production this can be backed by a
/// platform camera plugin, OpenCV bridge, or a native module. The contract stays
/// local and decoupled from the rest of the app.
class DeviceCameraSource implements CameraSource {
  DeviceCameraSource({
    required this.sourceId,
    required Stream<CameraFrameSample> stream,
    this.onError,
  }) : _stream = stream;

  final String sourceId;
  final Stream<CameraFrameSample> _stream;
  final void Function(Object error, StackTrace stackTrace)? onError;
  StreamSubscription<CameraFrameSample>? _subscription;

  @override
  Stream<CameraFrameSample> get frames => _stream;

  @override
  Future<void> start() async {
    await stop();
    _subscription = _stream.listen(
      (_) {},
      onError: (Object error, StackTrace stackTrace) {
        onError?.call(error, stackTrace);
      },
    );
  }

  @override
  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
  }
}

/// Converts a raw frame sample into the structured local VisionFrame contract.
class CameraFrameAdapter {
  CameraFrameAdapter({this.framePrefix = 'camera'});

  final String framePrefix;
  int _nextFrameId = 0;

  VisionFrame fromSample(CameraFrameSample sample) {
    final frameId = _nextFrameId++;
    return VisionFrame(
      frameId: frameId,
      timestamp: sample.timestamp,
      width: sample.width,
      height: sample.height,
      source: sample.source,
      payload: sample.payload,
      metadata: {
        ...sample.metadata,
        'framePrefix': framePrefix,
        'frameId': frameId,
      },
    );
  }
}

/// Performance and resilience metrics for camera streaming.
class CameraStreamMetrics {
  const CameraStreamMetrics({
    required this.framesProcessed,
    required this.fps,
    required this.averageLatencyMs,
    required this.lastLatencyMs,
  });

  final int framesProcessed;
  final double fps;
  final double averageLatencyMs;
  final double lastLatencyMs;
}

/// Camera stream binding that translates a local camera source into structured
/// VisionFrame objects and can forward them to the existing hazard engine.
class CameraStreamBinding {
  CameraStreamBinding({
    required CameraSource source,
    CameraFrameAdapter? adapter,
    Duration? measurementWindow,
    this.maxFramesPerSecond = 30,
    EdgePerformanceMonitor? performanceMonitor,
  })  : _source = source,
        _adapter = adapter ?? CameraFrameAdapter(),
        _measurementWindow = measurementWindow ?? const Duration(seconds: 5),
        _frameCounter = 0,
        _performanceMonitor = performanceMonitor ?? EdgePerformanceMonitor();

  final CameraSource _source;
  final CameraFrameAdapter _adapter;
  final Duration _measurementWindow;
  final int maxFramesPerSecond;
  final EdgePerformanceMonitor _performanceMonitor;
  int _frameCounter;
  DateTime? _lastFrameStamp;
  final List<int> _latencyBuckets = <int>[];
  StreamSubscription<CameraFrameSample>? _subscription;
  int _lastEmissionMs = 0;

  bool _isRunning = false;

  bool get isRunning => _isRunning;

  CameraStreamMetrics get metrics {
    final processed = _frameCounter;
    if (processed <= 0) {
      return const CameraStreamMetrics(
        framesProcessed: 0,
        fps: 0,
        averageLatencyMs: 0,
        lastLatencyMs: 0,
      );
    }

    final averageLatency = _latencyBuckets.isEmpty
        ? 0.0
        : _latencyBuckets.reduce((a, b) => a + b) / _latencyBuckets.length;

    final elapsedSeconds = _measurementWindow.inMilliseconds / 1000.0;
    final fps = processed / elapsedSeconds;

    return CameraStreamMetrics(
      framesProcessed: processed,
      fps: fps,
      averageLatencyMs: averageLatency,
      lastLatencyMs: _latencyBuckets.isEmpty ? 0.0 : _latencyBuckets.last.toDouble(),
    );
  }

  Future<void> start({
    required void Function(VisionFrame frame) onFrame,
    void Function(Object error, StackTrace stackTrace)? onError,
  }) async {
    if (_isRunning) {
      return;
    }

    try {
      await _source.start();
      _isRunning = true;
      _subscription = _source.frames.listen(
        (sample) {
          final nowMs = DateTime.now().millisecondsSinceEpoch;
          final minFrameIntervalMs = (1000 / maxFramesPerSecond).floor();
          if (minFrameIntervalMs > 0 &&
              _lastEmissionMs != 0 &&
              nowMs - _lastEmissionMs < minFrameIntervalMs) {
            return;
          }

          _lastEmissionMs = nowMs;
          final sampleCaptureAt = sample.timestamp.millisecondsSinceEpoch;
          final latencyMs = (nowMs - sampleCaptureAt).abs();
          _latencyBuckets.add(latencyMs);
          _frameCounter += 1;
          _lastFrameStamp = sample.timestamp;
          _performanceMonitor.recordFrame(latencyMs: latencyMs);

          final frame = _adapter.fromSample(sample);
          unawaited(Future<void>.microtask(() => onFrame(frame)));
        },
        onError: (Object error, StackTrace stackTrace) {
          onError?.call(error, stackTrace);
        },
        cancelOnError: false,
      );
    } on Exception catch (error, stackTrace) {
      _isRunning = false;
      onError?.call(error, stackTrace);
    }
  }

  Future<void> stop() async {
    if (!_isRunning) {
      return;
    }

    _isRunning = false;
    await _subscription?.cancel();
    _subscription = null;
    _lastEmissionMs = 0;
    await _source.stop();
  }
}

/// Adapt the new local camera abstraction to the legacy hazard engine's LocalFrameSource
/// contract. This keeps the offline pipeline fully compatible while allowing the new
/// camera binding layer to plug in cleanly.
class CameraSourceToLocalFrameAdapter implements hazard.LocalFrameSource {
  CameraSourceToLocalFrameAdapter({
    required CameraSource source,
    String cacheDirectory = '/tmp/ego_camera_frames',
    CameraFrameAdapter? adapter,
    this.persistFrames = false,
  })  : _source = source,
        _cacheDirectory = cacheDirectory,
        _adapter = adapter ?? CameraFrameAdapter(),
        _counter = 0;

  final CameraSource _source;
  final String _cacheDirectory;
  final CameraFrameAdapter _adapter;
  final bool persistFrames;
  int _counter;

  @override
  Stream<hazard.VisionFrame> get frameStream => _source.frames.asyncMap((sample) async {
    final frame = _adapter.fromSample(sample);
    String path = '';

    if (persistFrames) {
      final dir = Directory(_cacheDirectory);
      await dir.create(recursive: true);

      final fileName = 'frame_${frame.frameId}_${sample.timestamp.millisecondsSinceEpoch}.bin';
      path = p.join(dir.path, fileName);
      await File(path).writeAsBytes(frame.payload, flush: true);
    }

    return hazard.VisionFrame(
      captureAt: frame.timestamp,
      filePath: path.isEmpty ? sample.source : path,
      width: frame.width,
      height: frame.height,
      deviceId: frame.source,
      metadata: {
        ...frame.metadata,
        'framePayloadLength': frame.payload.length,
        'rawSource': frame.source,
      },
    );
  });
}

String _jsonEncode(Object value) => const JsonEncoder.withIndent('  ').convert(value);
