import 'dart:async';
import 'dart:developer' as developer;

/// Lightweight local telemetry for frame-processing performance.
class EdgePerformanceMonitor {
  EdgePerformanceMonitor({
    this.sampleWindow = const Duration(seconds: 5),
  });

  final Duration sampleWindow;
  final List<int> _latencies = <int>[];
  DateTime? _lastTick;
  int _totalFrames = 0;
  int _lastFrameCount = 0;
  int _maxLatency = 0;

  void recordFrame({required int latencyMs}) {
    _latencies.add(latencyMs);
    _totalFrames += 1;
    if (latencyMs > _maxLatency) {
      _maxLatency = latencyMs;
    }

    final now = DateTime.now();
    if (_lastTick == null) {
      _lastTick = now;
      return;
    }

    if (now.difference(_lastTick!) >= sampleWindow) {
      final avg = _latencies.isEmpty
          ? 0
          : _latencies.reduce((a, b) => a + b) ~/ _latencies.length;
      final elapsedMs = now.difference(_lastTick!).inMilliseconds;
      final fps = elapsedMs <= 0
          ? 0.0
          : ((_totalFrames - _lastFrameCount) / elapsedMs) * 1000;
      developer.log(
        'edge_perf frame_stats: ${fps.toStringAsFixed(2)} fps avg_latency_ms=$avg max_latency_ms=$_maxLatency',
        name: 'ego.performance',
      );
      _lastTick = now;
      _lastFrameCount = _totalFrames;
      _latencies.clear();
      _maxLatency = 0;
    }
  }

  Map<String, Object> snapshot() {
    final avgLatencyMs = _latencies.isEmpty
        ? 0
        : _latencies.reduce((a, b) => a + b) ~/ _latencies.length;

    return <String, Object>{
      'framesProcessed': _totalFrames,
      'avgLatencyMs': avgLatencyMs,
      'maxLatencyMs': _maxLatency,
      'sampleWindowMs': sampleWindow.inMilliseconds,
    };
  }
}
