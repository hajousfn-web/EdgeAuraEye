import 'dart:developer' as developer;

typedef DatabaseOperation<T> = Future<T> Function();
typedef DatabaseErrorLogger = void Function(
  String operation,
  Object error,
  StackTrace stackTrace,
);

/// Runs a local operation without allowing recoverable database exceptions to
/// escape into UI or background-worker code.
class SafeDatabaseOperation {
  const SafeDatabaseOperation({DatabaseErrorLogger? logger})
      : _logger = logger ?? _defaultLogger;

  final DatabaseErrorLogger _logger;

  Future<T> run<T>({
    required String operation,
    required DatabaseOperation<T> action,
    required T fallback,
  }) async {
    try {
      return await action();
    } on Exception catch (error, stackTrace) {
      _logger(operation, error, stackTrace);
      return fallback;
    }
  }

  void report(String operation, Object error, StackTrace stackTrace) {
    _logger(operation, error, stackTrace);
  }

  static void _defaultLogger(
    String operation,
    Object error,
    StackTrace stackTrace,
  ) {
    developer.log(
      'Local database operation failed: $operation',
      name: 'ego.local_database',
      error: error,
      stackTrace: stackTrace,
    );
  }
}
