import 'dart:io';

import 'package:drift/native.dart';
import 'package:ego_local_database/ego_local_database.dart';

Future<void> main() async {
  final database = EgoDatabase(NativeDatabase.memory());
  final repository = EgoLocalRepository(database);
  final workspace = await Directory.systemTemp.createTemp('ego_vision_test_');

  try {
    final rawFile = File('${workspace.path}${Platform.pathSeparator}raw.frame');
    final rawBytes = List<int>.generate(128, (index) => index);
    await rawFile.writeAsBytes(rawBytes, flush: true);

    final pipeline = EgoVisionPipeline(
      anonymizer: SimulatedLocalAnonymizer(),
      anonymizedDirectory:
          '${workspace.path}${Platform.pathSeparator}anonymized',
    );

    final anonymizedPath = await pipeline.processAndLog(
      frame: CapturedFrame(
        rawPath: rawFile.path,
        capturedAt: DateTime.utc(2026, 8, 30, 21, 0),
      ),
      repository: repository,
      latitude: 33.5731,
      longitude: -7.5898,
    );

    _check(anonymizedPath != null, 'pipeline returned an anonymized path');
    final anonymizedFile = File(anonymizedPath!);
    _check(await anonymizedFile.exists(), 'anonymized file was created');
    _check(
      _sameBytes(await rawFile.readAsBytes(), rawBytes),
      'original raw file remains unchanged',
    );
    _check(
      !_sameBytes(await anonymizedFile.readAsBytes(), rawBytes),
      'anonymized output differs from the raw frame',
    );

    final pendingBeforeSync = await repository.fetchPendingBlackboxEvents();
    _check(pendingBeforeSync.length == 1, 'blackbox event was persisted locally');
    _check(
      pendingBeforeSync.single.localVideoPath == anonymizedFile.path,
      'database stores the anonymized path only',
    );

    final transport = _RecordingTransport(
      rawPath: rawFile.path,
      expectedAnonymizedPath: anonymizedFile.path,
    );
    final engine = EgoVisionAndSyncEngine(
      repository: repository,
      networkStatus: _AlwaysOnline(),
      transport: transport,
    );

    await engine.runOnce();
    _check(transport.uploadCount == 1, 'one anonymized event was uploaded');
    _check(
      transport.lastPayload?.anonymizedVideoPath == anonymizedFile.path,
      'transport received anonymized metadata only',
    );
    _check(
      (await repository.fetchPendingBlackboxEvents()).isEmpty,
      'successful upload marked the event as synced',
    );

    await engine.runOnce();
    _check(transport.uploadCount == 1, 'synced event is not uploaded twice');
    print('Ego vision and sync integration test passed.');
  } finally {
    await database.close();
    await workspace.delete(recursive: true);
  }
}

class _AlwaysOnline implements NetworkStatus {
  @override
  Future<bool> isOnline() async => true;
}

class _RecordingTransport implements AnonymizedSyncTransport {
  _RecordingTransport({
    required this.rawPath,
    required this.expectedAnonymizedPath,
  });

  final String rawPath;
  final String expectedAnonymizedPath;
  int uploadCount = 0;
  AnonymizedBlackboxPayload? lastPayload;

  @override
  Future<bool> sendBlackboxEvent(AnonymizedBlackboxPayload payload) async {
    _check(
      payload.anonymizedVideoPath != rawPath,
      'transport never receives the raw path',
    );
    _check(
      payload.anonymizedVideoPath == expectedAnonymizedPath,
      'transport receives the generated anonymized path',
    );
    _check(
      payload.idempotencyKey == 'blackbox:${payload.id}',
      'transport receives a stable idempotency key',
    );
    lastPayload = payload;
    uploadCount++;
    print(
      'Simulated upload: id=${payload.id}, '
      'anonymizedPath=${payload.anonymizedVideoPath}',
    );
    return true;
  }
}

void _check(bool condition, String description) {
  if (!condition) {
    throw StateError('FAILED: $description');
  }
  print('OK: $description');
}

bool _sameBytes(List<int> left, List<int> right) {
  if (left.length != right.length) return false;
  for (var index = 0; index < left.length; index++) {
    if (left[index] != right[index]) return false;
  }
  return true;
}
