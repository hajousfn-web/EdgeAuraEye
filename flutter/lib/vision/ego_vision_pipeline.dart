import 'dart:developer' as developer;
import 'dart:io';

import 'package:path/path.dart' as p;

import '../repositories/ego_local_repository.dart';

/// A frame captured by the camera adapter. The adapter owns the raw capture.
class CapturedFrame {
  const CapturedFrame({
    required this.rawPath,
    required this.capturedAt,
  });

  final String rawPath;
  final DateTime capturedAt;
}

/// Implement this with a native ML/Core Image/OpenCV pipeline in production.
abstract interface class LocalAnonymizer {
  Future<void> anonymize({
    required String rawPath,
    required String anonymizedPath,
  });
}

/// Deterministic placeholder for integration tests and early platform work.
/// It must not be used as a real face or plate detector.
class SimulatedLocalAnonymizer implements LocalAnonymizer {
  @override
  Future<void> anonymize({
    required String rawPath,
    required String anonymizedPath,
  }) async {
    final input = await File(rawPath).readAsBytes();
    if (input.isEmpty) {
      throw const FormatException('Cannot anonymize an empty frame');
    }

    // Simulates pixelation by replacing each block with its first byte.
    final output = List<int>.from(input);
    for (var offset = 0; offset < output.length; offset += 16) {
      final end = offset + 16 < output.length ? offset + 16 : output.length;
      for (var index = offset + 1; index < end; index++) {
        output[index] = output[offset];
      }
    }
    await File(anonymizedPath).writeAsBytes(output, flush: true);
  }
}

/// Runs privacy processing before an event is made visible to the repository.
class EgoVisionPipeline {
  EgoVisionPipeline({
    required LocalAnonymizer anonymizer,
    required String anonymizedDirectory,
    void Function(Object error, StackTrace stackTrace)? onError,
  })  : _anonymizer = anonymizer,
        _anonymizedDirectory = anonymizedDirectory,
        _onError = onError ?? _defaultErrorHandler;

  final LocalAnonymizer _anonymizer;
  final String _anonymizedDirectory;
  final void Function(Object error, StackTrace stackTrace) _onError;

  Future<String?> processAndLog({
    required CapturedFrame frame,
    required EgoLocalRepository repository,
    required double latitude,
    required double longitude,
  }) async {
    try {
      await Directory(_anonymizedDirectory).create(recursive: true);
      final fileName =
          '${frame.capturedAt.microsecondsSinceEpoch}_${_fileName(frame.rawPath)}';
      final anonymizedPath = p.join(_anonymizedDirectory, fileName);

      // The raw path is never passed to the repository or sync payload.
      await _anonymizer.anonymize(
        rawPath: frame.rawPath,
        anonymizedPath: anonymizedPath,
      );
      final insertedId = await repository.logBlackboxEvent(
        eventTimestamp: frame.capturedAt,
        latitude: latitude,
        longitude: longitude,
        localVideoPath: anonymizedPath,
        isProcessedLocalBlur: true,
      );
      return insertedId == 0 ? null : anonymizedPath;
    } on Exception catch (error, stackTrace) {
      _onError(error, stackTrace);
      return null;
    }
  }

  static String _fileName(String path) =>
      path.split(RegExp(r'[/\\]')).last.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');

  static void _defaultErrorHandler(Object error, StackTrace stackTrace) {
    developer.log(
      'Local vision pipeline failed',
      name: 'ego.vision',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
