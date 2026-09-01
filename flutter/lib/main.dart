import 'package:flutter/material.dart';

import 'database/database.dart';
import 'repositories/ego_local_repository.dart';
import 'services/ego_telemetry_service.dart';
import 'ui/hud_entry.dart';
import 'vision/ego_hazard_capture_engine.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    final database = await openEgoDatabase();
    final repository = EgoLocalRepository(database);
    final telemetryService = EgoTelemetryService(database: database);
    final hazardCaptureEngine = EgoHazardCaptureEngine(
      frameSource: _NoopFrameSource(),
      telemetryService: telemetryService,
      captureLoop: LocalHazardCaptureLoop(
        telemetryService: telemetryService,
        captureDirectory: '/tmp/ego_capture',
      ),
    );

    runApp(EgoApp(
      database: database,
      repository: repository,
      telemetryService: telemetryService,
      hazardCaptureEngine: hazardCaptureEngine,
    ));
  } on Exception catch (error, stackTrace) {
    runApp(EgoBootstrapFailure(error: error, stackTrace: stackTrace));
  }
}

class _NoopFrameSource implements LocalFrameSource {
  const _NoopFrameSource();

  @override
  Stream<VisionFrame> get frameStream => const Stream.empty();
}

class EgoApp extends StatelessWidget {
  const EgoApp({
    required this.database,
    required this.repository,
    required this.telemetryService,
    required this.hazardCaptureEngine,
    super.key,
  });

  final EgoLocalDatabase database;
  final EgoLocalRepository repository;
  final EgoTelemetryService telemetryService;
  final EgoHazardCaptureEngine hazardCaptureEngine;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ego',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorSchemeSeed: Colors.teal,
        useMaterial3: true,
      ),
      home: EgoHudEntry(
        database: database,
        telemetryService: telemetryService,
        hazardCaptureEngine: hazardCaptureEngine,
      ),
    );
  }
}

class EgoHomePage extends StatelessWidget {
  const EgoHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.shield_outlined,
                color: Theme.of(context).colorScheme.primary,
                size: 72,
              ),
              const SizedBox(height: 24),
              Text(
                'Ego',
                style: Theme.of(context).textTheme.displaySmall,
              ),
              const SizedBox(height: 12),
              Text(
                'Phase 1 Active & Secure',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                'Encrypted offline storage is ready.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class EgoBootstrapFailure extends StatelessWidget {
  const EgoBootstrapFailure({
    required this.error,
    required this.stackTrace,
    super.key,
  });

  final Object error;
  final StackTrace stackTrace;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ego',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorSchemeSeed: Colors.red,
        useMaterial3: true,
      ),
      home: Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'Ego could not initialize secure local storage.\n\n'
              'Please restart the application or contact support.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ),
      ),
    );
  }
}
