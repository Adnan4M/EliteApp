import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';
import '../api/api_client.dart';
import '../config.dart' show AcademicYear;

/// Holds the auth token, persists it securely, and exposes the [Api].
class AuthController extends ChangeNotifier {
  static const _tokenKey = 'elite_token';
  static const _semesterKey = 'selected_semester';
  static const _yearKey = 'selected_year';

  final _storage = const FlutterSecureStorage();
  final ApiClient _client = ApiClient();
  late final Api api = Api(_client);

  String? _token;
  bool _loading = true;
  String _year = 'prep';
  String _semester = 'first';
  // Format: "year:semester" e.g. "prep:first"
  List<String> _activatedSemesters = [];
  // Years the backend reports as having content. Empty until /me responds;
  // the UI must not offer a year picker while this holds fewer than 2 entries.
  List<AcademicYear> _availableYears = const [];

  bool get isLoading => _loading;
  bool get isAuthenticated => _token != null;
  String? get token => _token;
  String get year => _year;
  String get semester => _semester;
  List<String> get activatedSemesters => _activatedSemesters;
  List<AcademicYear> get availableYears => _availableYears;

  /// Only offer a year switcher once the admin has released a second year.
  bool get showYearPicker => _availableYears.length > 1;

  void setAvailableYears(List<AcademicYear> years) {
    _availableYears = years;
    // Never leave the user parked on a year the backend no longer serves.
    if (years.isNotEmpty && !years.any((y) => y.id == _year)) {
      setYear(years.first.id);
    } else {
      notifyListeners();
    }
  }

  /// Returns activated semesters for the current year only.
  List<String> get activatedSemestersForYear =>
      _activatedSemesters
          .where((s) => s.startsWith('$_year:'))
          .map((s) => s.split(':')[1])
          .toList();

  void setActivatedSemesters(List<String> semesters) {
    _activatedSemesters = semesters;
    final forYear = activatedSemestersForYear;
    if (forYear.isNotEmpty && !forYear.contains(_semester)) {
      setSemester(forYear.first);
    } else {
      notifyListeners();
    }
  }

  Future<void> setYear(String value) async {
    if (_year == value) return;
    _year = value;
    // Reset semester to first when switching years
    _semester = 'first';
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_yearKey, value);
    await prefs.setString(_semesterKey, _semester);
  }

  Future<void> setSemester(String value) async {
    if (_semester == value) return;
    _semester = value;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_semesterKey, value);
  }

  int? get userId {
    if (_token == null) return null;
    try {
      final parts = _token!.split('.');
      if (parts.length != 3) return null;
      final payload = utf8.decode(
          base64Url.decode(base64Url.normalize(parts[1])));
      final data = jsonDecode(payload) as Map<String, dynamic>;
      final sub = data['sub'];
      return sub is int ? sub : int.tryParse(sub.toString());
    } catch (_) {
      return null;
    }
  }

  /// Restore a saved token, year, and semester on app start.
  Future<void> bootstrap() async {
    _token = await _storage.read(key: _tokenKey);
    _client.setToken(_token);
    final prefs = await SharedPreferences.getInstance();
    _year = prefs.getString(_yearKey) ?? 'prep';
    _semester = prefs.getString(_semesterKey) ?? 'first';
    _loading = false;
    notifyListeners();
  }

  Future<void> _persist(String token) async {
    _token = token;
    _client.setToken(token);
    await _storage.write(key: _tokenKey, value: token);
    notifyListeners();
  }

  Future<void> register(String email, String password,
      {String? name, String? phone}) async {
    await api.register(email, password, name: name, phone: phone);
  }

  Future<void> loginWithToken(String token) async {
    await _persist(token);
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
