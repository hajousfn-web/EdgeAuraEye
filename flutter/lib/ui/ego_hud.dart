import 'dart:async';
import 'dart:developer' as developer;
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../database/database.dart';
import '../services/ego_telemetry_service.dart';
import '../vision/ego_hazard_capture_engine.dart';

/// Local-only HUD state consumed reactively by the UI from database streams and
/// telemetry updates. This screen intentionally has zero cloud or hardware
/// coupling.
enum EgoHudMode { pedestrian, vehicle }

enum EgoAlertLevel { normal, warning, critical }

class EgoHudViewModel {
  const EgoHudViewModel({
    required this.mode,
    required this.alertLevel,
    required this.destinationLabel,
    required this.distanceToDestination,
    required this.currentSpeed,
    required this.accelerationDelta,
    required this.heading,
    required this.liveFrameLabel,
    required this.logs,
    required this.isConnected,
  });

  final EgoHudMode mode;
  final EgoAlertLevel alertLevel;
  final String destinationLabel;
  final double distanceToDestination;
  final double currentSpeed;
  final double accelerationDelta;
  final String heading;
  final String liveFrameLabel;
  final List<BlackboxEvent> logs;
  final bool isConnected;

  static const EgoHudViewModel idle = EgoHudViewModel(
    mode: EgoHudMode.pedestrian,
    alertLevel: EgoAlertLevel.normal,
    destinationLabel: 'Local route',
    distanceToDestination: 0,
    currentSpeed: 0,
    accelerationDelta: 0,
    heading: 'North',
    liveFrameLabel: 'Offline feed standby',
    logs: <BlackboxEvent>[],
    isConnected: true,
  );
}

class EgoHudController extends ChangeNotifier {
  EgoHudController({
    required EgoTelemetryService telemetryService,
    required EgoHazardCaptureEngine hazardCaptureEngine,
  })  : _telemetryService = telemetryService,
        _hazardCaptureEngine = hazardCaptureEngine {
    _watchPendingEvents();
  }

  final EgoTelemetryService _telemetryService;
  final EgoHazardCaptureEngine _hazardCaptureEngine;

  EgoHudMode _mode = EgoHudMode.pedestrian;
  EgoAlertLevel _alertLevel = EgoAlertLevel.normal;
  String _destinationLabel = 'Local route';
  double _distanceToDestination = 0;
  double _currentSpeed = 0;
  double _accelerationDelta = 0;
  String _heading = 'North';
  String _liveFrameLabel = 'Offline feed standby';
  List<BlackboxEvent> _logs = <BlackboxEvent>[];
  bool _isConnected = true;
  StreamSubscription<List<BlackboxEvent>>? _pendingSubscription;

  EgoHudMode get mode => _mode;
  EgoAlertLevel get alertLevel => _alertLevel;
  String get destinationLabel => _destinationLabel;
  double get distanceToDestination => _distanceToDestination;
  double get currentSpeed => _currentSpeed;
  double get accelerationDelta => _accelerationDelta;
  String get heading => _heading;
  String get liveFrameLabel => _liveFrameLabel;
  List<BlackboxEvent> get logs => _logs;
  bool get isConnected => _isConnected;

  void setMode(EgoHudMode mode) {
    if (_mode == mode) return;
    _mode = mode;
    _destinationLabel = mode == EgoHudMode.pedestrian ? 'Route to safe waypoint' : 'Vehicle route lock';
    notifyListeners();
  }

  Future<void> refreshTelemetry() async {
    final pending = await _telemetryService.getPendingBlackboxEvents();
    _logs = pending;
    _alertLevel = _calculateAlertLevel();
    notifyListeners();
  }

  Future<void> _watchPendingEvents() async {
    _pendingSubscription = _telemetryService.watchPendingBlackboxEvents().listen(
      (events) {
        _logs = events;
        _alertLevel = _calculateAlertLevel();
        notifyListeners();
      },
      onError: (Object error, StackTrace stackTrace) {
        developer.log(
          'HUD blackbox stream failed',
          name: 'ego.hud',
          error: error,
          stackTrace: stackTrace,
        );
      },
      cancelOnError: false,
    );
  }

  void updateTelemetry({
    required double speed,
    required double accelerationDelta,
    required double distanceToDestination,
    required String heading,
  }) {
    _currentSpeed = speed;
    _accelerationDelta = accelerationDelta;
    _distanceToDestination = distanceToDestination;
    _heading = heading;
    _alertLevel = _calculateAlertLevel();
    notifyListeners();
  }

  void updateFrameLabel(String label) {
    _liveFrameLabel = label;
    notifyListeners();
  }

  EgoAlertLevel _calculateAlertLevel() {
    final hasCritical = _logs.any((event) => event.isProcessedLocalBlur && event.syncStatus == pendingSync);
    if (hasCritical || _accelerationDelta.abs() > 3.5) {
      return EgoAlertLevel.critical;
    }
    if (_accelerationDelta.abs() > 1.5 || _distanceToDestination < 25) {
      return EgoAlertLevel.warning;
    }
    return EgoAlertLevel.normal;
  }

  EgoHudViewModel buildViewModel() {
    return EgoHudViewModel(
      mode: _mode,
      alertLevel: _alertLevel,
      destinationLabel: _destinationLabel,
      distanceToDestination: _distanceToDestination,
      currentSpeed: _currentSpeed,
      accelerationDelta: _accelerationDelta,
      heading: _heading,
      liveFrameLabel: _liveFrameLabel,
      logs: _logs,
      isConnected: _isConnected,
    );
  }

  @override
  void dispose() {
    _pendingSubscription?.cancel();
    super.dispose();
  }
}

class EgoHudScreen extends StatefulWidget {
  const EgoHudScreen({
    required this.telemetryService,
    required this.hazardCaptureEngine,
    super.key,
  });

  final EgoTelemetryService telemetryService;
  final EgoHazardCaptureEngine hazardCaptureEngine;

  @override
  State<EgoHudScreen> createState() => _EgoHudScreenState();
}

class _EgoHudScreenState extends State<EgoHudScreen> {
  late final EgoHudController _controller;

  @override
  void initState() {
    super.initState();
    _controller = EgoHudController(
      telemetryService: widget.telemetryService,
      hazardCaptureEngine: widget.hazardCaptureEngine,
    );

    _controller.addListener(_handleStateChange);
    _controller.updateTelemetry(
      speed: 0,
      accelerationDelta: 0,
      distanceToDestination: 120,
      heading: 'North',
    );
    _controller.updateFrameLabel('Local feed active');
  }

  void _handleStateChange() {
    if (mounted) {
      setState(() {});
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_handleStateChange);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final viewModel = _controller.buildViewModel();
    final theme = Theme.of(context);
    final colors = theme.colorScheme;

    return Scaffold(
      backgroundColor: const Color(0xFF07151A),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Row(
          children: [
            Icon(Icons.sensors, color: colors.primary),
            const SizedBox(width: 10),
            Text(
              'Ego Local HUD',
              style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
            ),
          ],
        ),
        actions: [
          SegmentedButton<EgoHudMode>(
            segments: const <ButtonSegment<EgoHudMode>>[
              ButtonSegment<EgoHudMode>(
                value: EgoHudMode.pedestrian,
                icon: Icon(Icons.directions_walk),
                label: Text('Pedestrian'),
              ),
              ButtonSegment<EgoHudMode>(
                value: EgoHudMode.vehicle,
                icon: Icon(Icons.drive_eta),
                label: Text('Vehicle'),
              ),
            ],
            selected: <EgoHudMode>{_controller.mode},
            onSelectionChanged: (Set<EgoHudMode> value) {
              if (value.isNotEmpty) {
                _controller.setMode(value.first);
              }
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              _AlertBanner(level: viewModel.alertLevel),
              const SizedBox(height: 12),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 2,
                      child: Column(
                        children: [
                          _NavigationCard(viewModel: viewModel),
                          const SizedBox(height: 12),
                          _LiveCameraViewport(label: viewModel.liveFrameLabel),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        children: [
                          _StatusPanel(viewModel: viewModel),
                          const SizedBox(height: 12),
                          _RecentEventsPanel(events: viewModel.logs),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AlertBanner extends StatelessWidget {
  const _AlertBanner({required this.level});

  final EgoAlertLevel level;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    Color background;
    String label;
    IconData icon;

    switch (level) {
      case EgoAlertLevel.normal:
        background = const Color(0xFF1B3A2F);
        label = 'Normal local conditions';
        icon = Icons.check_circle_outline;
      case EgoAlertLevel.warning:
        background = const Color(0xFF453313);
        label = 'Warning: proximity risk';
        icon = Icons.warning_amber_rounded;
      case EgoAlertLevel.critical:
        background = const Color(0xFF4A1C1C);
        label = 'Critical hazard detected';
        icon = Icons.error_outline_rounded;
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.primary.withOpacity(0.35)),
      ),
      child: Row(
        children: [
          Icon(icon, color: Colors.white),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _NavigationCard extends StatelessWidget {
  const _NavigationCard({required this.viewModel});

  final EgoHudViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final bool isPedestrian = viewModel.mode == EgoHudMode.pedestrian;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0F1C23),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: primary.withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isPedestrian ? Icons.directions_walk : Icons.drive_eta,
                color: primary,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  isPedestrian ? 'Pedestrian Route' : 'Vehicle / Operator Tracking',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                viewModel.destinationLabel,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              Text(
                '${viewModel.distanceToDestination.toStringAsFixed(0)} m',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Container(
            height: 96,
            decoration: BoxDecoration(
              color: const Color(0xFF10242D),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Center(
                    child: Icon(
                      _directionIcon(viewModel.heading),
                      size: 42,
                      color: primary,
                    ),
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          'Heading',
                          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: Colors.white70,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          viewModel.heading,
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _directionIcon(String heading) {
    switch (heading.toLowerCase()) {
      case 'north':
        return Icons.north;
      case 'south':
        return Icons.south;
      case 'east':
        return Icons.east;
      case 'west':
        return Icons.west;
      default:
        return Icons.navigation;
    }
  }
}

class _StatusPanel extends StatelessWidget {
  const _StatusPanel({required this.viewModel});

  final EgoHudViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final stats = <_MetricTileData>[
      _MetricTileData(label: 'Speed', value: '${viewModel.currentSpeed.toStringAsFixed(1)} m/s'),
      _MetricTileData(label: 'Accel Δ', value: '${viewModel.accelerationDelta.toStringAsFixed(2)} g'),
      _MetricTileData(label: 'Mode', value: viewModel.mode.name),
      _MetricTileData(label: 'Status', value: viewModel.alertLevel.name),
    ];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0E1C21),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Live telemetry',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: 12),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: stats.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 10,
              mainAxisSpacing: 10,
              childAspectRatio: 1.5,
            ),
            itemBuilder: (context, index) {
              final stat = stats[index];
              return _MetricTile(stat: stat);
            },
          ),
        ],
      ),
    );
  }
}

class _MetricTileData {
  const _MetricTileData({required this.label, required this.value});

  final String label;
  final String value;
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.stat});

  final _MetricTileData stat;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF10242D),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            stat.label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: Colors.white70,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            stat.value,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _LiveCameraViewport extends StatelessWidget {
  const _LiveCameraViewport({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF0F1C23),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Theme.of(context).colorScheme.primary.withOpacity(0.2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.videocam_outlined, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Feed viewport',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF08171C),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.slow_motion_video_rounded,
                        size: 44,
                        color: Colors.white60,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        label,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RecentEventsPanel extends StatelessWidget {
  const _RecentEventsPanel({required this.events});

  final List<BlackboxEvent> events;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF0E1C21),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Recent events',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            if (events.isEmpty)
              Expanded(
                child: Center(
                  child: Text(
                    'No local blackbox records yet.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.white70,
                    ),
                  ),
                ),
              )
            else
              Expanded(
                child: ListView.builder(
                  itemCount: events.length,
                  itemBuilder: (context, index) {
                    final event = events[index];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFF10242D),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            event.syncStatus == 1 ? Icons.check_circle : Icons.pending_actions,
                            color: event.syncStatus == 1 ? Colors.greenAccent : Colors.amber,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Local hazard event',
                                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '${event.eventTimestamp.toLocal().toIso8601String()}\n'
                                  'Lat ${event.locationLatitude.toStringAsFixed(5)} • '
                                  'Lng ${event.locationLongitude.toStringAsFixed(5)}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
