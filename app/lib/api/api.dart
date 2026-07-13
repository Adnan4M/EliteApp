import '../config.dart';
import '../models.dart';
import 'api_client.dart';

/// Typed access to every backend endpoint the app uses.
class Api {
  final ApiClient client;
  Api(this.client);

  // -- auth ---------------------------------------------------------------
  Future<String> register(String email, String password, {String? name}) async {
    final j = await client.post('/auth/register', body: {
      'email': email,
      'password': password,
      if (name != null && name.isNotEmpty) 'name': name,
    });
    return j['access_token'] as String;
  }

  Future<String> login(String email, String password) async {
    final j = await client.post('/auth/login',
        body: {'email': email, 'password': password});
    return j['access_token'] as String;
  }

  // -- profile ------------------------------------------------------------
  Future<Profile> me(String semester) async {
    final j = await client.get('/me', query: {'semester': semester});
    return Profile.fromJson(j as Map<String, dynamic>);
  }

  Future<void> updateProgress({
    required String semester,
    required String subjectId,
    required String chapter,
    required double percent,
  }) async {
    await client.post('/progress', body: {
      'semester': semester,
      'subject_id': subjectId,
      'chapter': chapter,
      'percent': percent,
    });
  }

  // -- search -------------------------------------------------------------
  Future<List<String>> suggest(String semester, String q) async {
    final j = await client.get('/search/suggest',
        query: {'semester': semester, 'q': q});
    return (j['suggestions'] as List).map((e) => e.toString()).toList();
  }

  Future<SearchResult> search(String semester, String keyword) async {
    final j = await client
        .post('/search', query: {'semester': semester, 'keyword': keyword});
    return SearchResult.fromJson(j as Map<String, dynamic>);
  }

  String pageImageUrl(String queryId, int position) =>
      '${Config.apiBase}/search/page?query_id=$queryId&position=$position';

  Future<List<int>> pageImage(String queryId, int position) =>
      client.getBytes('/search/page',
          query: {'query_id': queryId, 'position': position});

  Future<String> summary(String semester, String keyword) async {
    final j = await client.post('/search/summary',
        query: {'semester': semester, 'keyword': keyword});
    return j['summary'] as String;
  }

  Future<Explanation> explanation(String semester, String keyword) async {
    final j = await client.post('/search/explanation',
        query: {'semester': semester, 'keyword': keyword});
    return Explanation.fromJson(j as Map<String, dynamic>);
  }

  Future<List<Mcq>> questions(String semester, String keyword,
      {int count = 5, bool refresh = false}) async {
    final j = await client.post('/search/questions', query: {
      'semester': semester,
      'keyword': keyword,
      'count': count,
      'refresh': refresh,
    });
    return (j['questions'] as List)
        .map((e) => Mcq.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // -- codes --------------------------------------------------------------
  Future<String> redeemCode(String code) async {
    final j = await client.post('/codes/redeem', body: {'code': code});
    return j['message'] as String;
  }

  // -- notifications / support -------------------------------------------
  Future<List<AppNotification>> notifications() async {
    final j = await client.get('/notifications');
    return (j as List)
        .map((e) => AppNotification.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String> supportUrl() async {
    final j = await client.get('/support');
    return j['telegram_url'] as String;
  }
}
