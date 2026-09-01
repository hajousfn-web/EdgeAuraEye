import 'package:flutter/material.dart';

import '../database/database.dart';
import '../services/ego_telemetry_service.dart';
import '../vision/ego_hazard_capture_engine.dart';
import 'ego_hud.dart';

class EgoHudEntry extends StatelessWidget {
  const EgoHudEntry({
    required this.database,
    required this.telemetryService,
    required this.hazardCaptureEngine,
    super.key,
  });

  final EgoDatabase database;
  final EgoTelemetryService telemetryService;
  final EgoHazardCaptureEngine hazardCaptureEngine;

  @override
  Widget build(BuildContext context) {
    return EgoHudScreen(
      telemetryService: telemetryService,
      hazardCaptureEngine: hazardCaptureEngine,
    );
  }
}
