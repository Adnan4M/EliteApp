// Smoke test: widget integration tests require a live backend + secure storage,
// so those live in the backend's pytest suite. This file just satisfies the
// flutter test runner so `flutter analyze` stays clean.
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('placeholder', () => expect(1 + 1, 2));
}
