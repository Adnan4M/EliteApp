import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config.dart';

/// Raised for any non-2xx response, carrying the HTTP status and server detail.
class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);

  bool get isUnauthorized => status == 401;
  bool get isPaymentRequired => status == 402; // semester not subscribed
  bool get isRateLimited => status == 429; // AI daily limit reached

  @override
  String toString() => 'ApiException($status): $message';
}

/// Thin HTTP wrapper that injects the bearer token and decodes JSON/errors.
class ApiClient {
  final http.Client _http;
  String? _token;

  ApiClient([http.Client? client]) : _http = client ?? http.Client();

  void setToken(String? token) => _token = token;

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse('${Config.apiBase}$path');
    if (query == null) return base;
    return base.replace(
      queryParameters: query.map((k, v) => MapEntry(k, '$v')),
    );
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    final res = await _http.get(_uri(path, query), headers: _headers);
    return _decode(res);
  }

  /// Most backend write endpoints take their inputs as query parameters.
  Future<dynamic> post(String path,
      {Map<String, dynamic>? query, Object? body}) async {
    final res = await _http.post(
      _uri(path, query),
      headers: _headers,
      body: body != null ? jsonEncode(body) : null,
    );
    return _decode(res);
  }

  /// Fetch raw bytes (used for rendered page images).
  Future<List<int>> getBytes(String path, {Map<String, dynamic>? query}) async {
    final res = await _http.get(_uri(path, query), headers: _headers);
    if (res.statusCode >= 200 && res.statusCode < 300) return res.bodyBytes;
    throw _error(res);
  }

  dynamic _decode(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.body.isEmpty) return null;
      return jsonDecode(utf8.decode(res.bodyBytes));
    }
    throw _error(res);
  }

  ApiException _error(http.Response res) {
    String detail = 'حدث خطأ (${res.statusCode})';
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      if (decoded is Map && decoded['detail'] != null) {
        detail = decoded['detail'].toString();
      }
    } catch (_) {}
    return ApiException(res.statusCode, detail);
  }
}
