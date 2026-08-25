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
  Future<Profile> me(String semester, {String year = 'prep'}) async {
    final j = await client.get('/me', query: {'semester': semester, 'year': year});
    return Profile.fromJson(j as Map<String, dynamic>);
  }

  Future<void> updateProgress({
    required String semester,
    required String subjectId,
    required String chapter,
    required double percent,
    String year = 'prep',
  }) async {
    await client.post('/progress', body: {
      'year': year,
      'semester': semester,
      'subject_id': subjectId,
      'chapter': chapter,
      'percent': percent,
    });
  }

  // -- search -------------------------------------------------------------
  Future<List<String>> suggest(String semester, String q, {String year = 'prep'}) async {
    final j = await client.get('/search/suggest',
        query: {'semester': semester, 'year': year, 'q': q});
    return (j['suggestions'] as List).map((e) => e.toString()).toList();
  }

  Future<SearchResult> search(String semester, String keyword, {String year = 'prep'}) async {
    final j = await client.post('/search',
        query: {'semester': semester, 'year': year, 'keyword': keyword});
    return SearchResult.fromJson(j as Map<String, dynamic>);
  }

  Future<List<int>> pageImage({
    required String semester,
    required String subjectId,
    required int page,
    required String query,
    String year = 'prep',
  }) =>
      client.getBytes('/search/page', query: {
        'semester': semester,
        'year': year,
        'subject_id': subjectId,
        'page': page,
        'query': query,
      });

  Future<String> summary(String semester, String keyword, {String year = 'prep'}) async {
    final j = await client.post('/search/summary',
        query: {'semester': semester, 'year': year, 'keyword': keyword});
    return j['summary'] as String;
  }

  Future<Explanation> explanation(String semester, String keyword, {String year = 'prep'}) async {
    final j = await client.post('/search/explanation',
        query: {'semester': semester, 'year': year, 'keyword': keyword});
    return Explanation.fromJson(j as Map<String, dynamic>);
  }

  Future<List<Mcq>> questions(String semester, String keyword,
      {int count = 5, bool refresh = false, String year = 'prep'}) async {
    final j = await client.post('/search/questions', query: {
      'semester': semester,
      'year': year,
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

  // -- XP / study curriculum ----------------------------------------------
  Future<UserXp> myXp() async {
    final j = await client.get('/study/xp');
    return UserXp.fromJson(j as Map<String, dynamic>);
  }

  Future<List<SubjectCurriculum>> curriculum({String semester = 'first', String year = 'prep'}) async {
    final j = await client.get('/study/curriculum', query: {'semester': semester, 'year': year}) as List;
    return j
        .map((e) => SubjectCurriculum.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<String>> myCompletions() async {
    final j = await client.get('/study/chapters') as List;
    return j
        .map((e) => (e as Map<String, dynamic>)['chapter_key'] as String)
        .toList();
  }

  Future<void> markChapterDone(
      String semester, String subjectId, String chapterKey) async {
    await client.post('/study/chapters/done', body: {
      'semester': semester,
      'subject_id': subjectId,
      'chapter_key': chapterKey,
    });
  }

  Future<void> unmarkChapter(
      String semester, String subjectId, String chapterKey) async {
    await client.delete('/study/chapters/done', query: {
      'semester': semester,
      'subject_id': subjectId,
      'chapter_key': chapterKey,
    });
  }

  // -- study pairs --------------------------------------------------------
  Future<List<StudyPair>> myPairs() async {
    final j = await client.get('/study/pairs') as List;
    return j
        .map((e) => StudyPair.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Create a new pair and get the invite code to share.
  Future<Map<String, dynamic>> createPair() async {
    final j = await client.post('/study/pair/create');
    return j as Map<String, dynamic>;
  }

  /// Join a pair using the 6-char invite code.
  Future<Map<String, dynamic>> joinPair(String code) async {
    final j = await client.post('/study/pair/join', body: {'code': code});
    return j as Map<String, dynamic>;
  }

  Future<void> leavePair(int pairId) async {
    await client.delete('/study/pair/$pairId');
  }

  Future<Map<String, dynamic>> pairProgress(int pairId) async {
    return await client.get('/study/pair/$pairId/progress')
        as Map<String, dynamic>;
  }

  // -- challenges ---------------------------------------------------------
  Future<Map<String, dynamic>> createChallenge({
    required String type,
    required String semester,
    required String subjectId,
    List<String> chapters = const [],
    int? partnerId,
    bool isPrivate = false,
    int questionCount = 10,
  }) async {
    final j = await client.post('/challenges', body: {
      'type': type,
      'semester': semester,
      'subject_id': subjectId,
      'chapters': chapters,
      'is_private': isPrivate,
      'question_count': questionCount,
      if (partnerId != null) 'partner_id': partnerId,
    });
    return j as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> pendingChallenges() async {
    final j = await client.get('/challenges/pending') as List;
    return j.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<List<Map<String, dynamic>>> myChallenges() async {
    final j = await client.get('/challenges/mine') as List;
    return j.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<List<OpenChallenge>> openChallenges({
    String? subjectId,
    String? semester,
  }) async {
    final j = await client.get('/challenges/open', query: {
      if (subjectId != null) 'subject_id': subjectId,
      if (semester != null) 'semester': semester,
    }) as List;
    return j
        .map((e) => OpenChallenge.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> joinChallenge(int challengeId, {String? inviteCode}) async {
    await client.post('/challenges/$challengeId/join',
        body: inviteCode != null ? {'invite_code': inviteCode} : {});
  }

  Future<int> joinChallengeByCode(String code) async {
    final j = await client.post('/challenges/join-by-code', body: {'code': code});
    return (j as Map<String, dynamic>)['challenge_id'] as int;
  }

  Future<Map<String, dynamic>> getChallenge(int challengeId) async {
    final j = await client.get('/challenges/$challengeId');
    return j as Map<String, dynamic>;
  }

  String challengeWsUrl(int challengeId, String token) {
    final base = Uri.parse(Config.apiBase);
    final wsScheme = base.scheme == 'https' ? 'wss' : 'ws';
    return '$wsScheme://${base.host}:${base.port}/challenges/ws/$challengeId?token=$token';
  }

  // -- store / skins -------------------------------------------------------
  Future<List<StoreSkin>> storeSkins() async {
    final j = await client.get('/store/skins') as List;
    return j.map((e) => StoreSkin.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Map<String, dynamic>> buySkin(int skinId) async {
    final j = await client.post('/store/buy/$skinId');
    return j as Map<String, dynamic>;
  }

  Future<void> equipSkin(int skinId) async {
    await client.post('/store/equip/$skinId');
  }

  Future<void> setGender(String gender) async {
    await client.post('/store/gender', body: {'gender': gender});
  }

  Future<WordOfDay> wordOfDay(String semester) async {
    final j = await client.get('/study/word-of-day', query: {'semester': semester});
    return WordOfDay.fromJson(j as Map<String, dynamic>);
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
