import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api.dart';
import '../api/api_client.dart';

/// Holds the auth token, persists it securely, and exposes the [Api].
class AuthController extends ChangeNotifier {
  static const _tokenKey = 'elite_token';

  final _storage = const FlutterSecureStorage();
  final ApiClient _client = ApiClient();
  late final Api api = Api(_client);

  String? _token;
  bool _loading = true;

  bool get isLoading => _loading;
  bool get isAuthenticated => _token != null;

  /// Restore a saved token on app start.
  Future<void> bootstrap() async {
    _token = await _storage.read(key: _tokenKey);
    _client.setToken(_token);
    _loading = false;
    notifyListeners();
  }

  Future<void> _persist(String token) async {
    _token = token;
    _client.setToken(token);
    await _storage.write(key: _tokenKey, value: token);
    notifyListeners();
  }

  Future<void> register(String email, String password, {String? name}) async {
    await _persist(await api.register(email, password, name: name));
  }

  Future<void> login(String email, String password) async {
    await _persist(await api.login(email, password));
  }

  Future<void> logout() async {
    _token = null;
    _client.setToken(null);
    await _storage.delete(key: _tokenKey);
    notifyListeners();
  }

  /// Called by screens when a request returns 401.
  Future<void> handleUnauthorized(Object error) async {
    if (error is ApiException && error.isUnauthorized) {
      await logout();
    }
  }
}
