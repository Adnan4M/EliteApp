/// Data models mirroring the backend's JSON responses.
library;

import 'config.dart' show AcademicYear;

class SubjectProgress {
  final String subjectId;
  final String nameAr;
  final String nameEn;
  final double percent;
  final bool locked;

  SubjectProgress({
    required this.subjectId,
    required this.nameAr,
    required this.nameEn,
    required this.percent,
    required this.locked,
  });

  factory SubjectProgress.fromJson(Map<String, dynamic> j) => SubjectProgress(
        subjectId: j['subject_id'] as String,
        nameAr: j['name_ar'] as String,
        nameEn: j['name_en'] as String,
        percent: (j['percent'] as num).toDouble(),
        locked: j['locked'] as bool,
      );
}

class SkinInfo {
  final int id;
  final String nameAr;
  final String emoji;
  final String bgColor;

  SkinInfo({required this.id, required this.nameAr, required this.emoji, required this.bgColor});

  factory SkinInfo.fromJson(Map<String, dynamic> j) => SkinInfo(
        id: j['id'] as int,
        nameAr: j['name_ar'] as String,
        emoji: j['emoji'] as String,
        bgColor: j['bg_color'] as String,
      );
}

class Profile {
  final String? name;
  final String email;
  final String year;
  final String currentSemester;
  final List<String> activatedSemesters;
  /// Years the backend says actually have content. Render only these.
  final List<AcademicYear> availableYears;
  final List<SubjectProgress> subjects;
  final int? rank;
  final int totalStudents;
  final String? gender;
  final SkinInfo? activeSkin;
  final int xp;

  Profile({
    required this.name,
    required this.email,
    required this.year,
    required this.currentSemester,
    this.activatedSemesters = const [],
    this.availableYears = const [],
    required this.subjects,
    required this.rank,
    required this.totalStudents,
    this.gender,
    this.activeSkin,
    this.xp = 0,
  });

  factory Profile.fromJson(Map<String, dynamic> j) => Profile(
        name: j['name'] as String?,
        email: j['email'] as String,
        year: j['year'] as String,
        currentSemester: j['current_semester'] as String,
        activatedSemesters: (j['activated_semesters'] as List? ?? [])
            .map((e) => e as String)
            .toList(),
        availableYears: (j['available_years'] as List? ?? [])
            .map((e) => AcademicYear(
                  id: (e as Map<String, dynamic>)['id'] as String,
                  labelAr: e['label_ar'] as String,
                ))
            .toList(),
        subjects: (j['subjects'] as List)
            .map((e) => SubjectProgress.fromJson(e as Map<String, dynamic>))
            .toList(),
        rank: j['rank'] as int?,
        totalStudents: j['total_students'] as int,
        gender: j['gender'] as String?,
        activeSkin: j['active_skin'] != null
            ? SkinInfo.fromJson(j['active_skin'] as Map<String, dynamic>)
            : null,
        xp: (j['xp'] as num? ?? 0).toInt(),
      );
}

class WordOfDay {
  final String word;
  final String definition;
  final String example;
  final String date;
  final String semester;

  WordOfDay({
    required this.word,
    required this.definition,
    required this.example,
    required this.date,
    this.semester = 'first',
  });

  factory WordOfDay.fromJson(Map<String, dynamic> j) => WordOfDay(
        word: j['word'] as String? ?? '',
        definition: j['definition'] as String? ?? '',
        example: j['example'] as String? ?? '',
        date: j['date'] as String? ?? '',
        semester: j['semester'] as String? ?? 'first',
      );
}

class StoreSkin {
  final int id;
  final String nameAr;
  final String emoji;
  final String bgColor;
  final int priceXp;
  final String? gender;
  final bool owned;
  final bool active;

  StoreSkin({
    required this.id,
    required this.nameAr,
    required this.emoji,
    required this.bgColor,
    required this.priceXp,
    this.gender,
    required this.owned,
    required this.active,
  });

  factory StoreSkin.fromJson(Map<String, dynamic> j) => StoreSkin(
        id: j['id'] as int,
        nameAr: j['name_ar'] as String,
        emoji: j['emoji'] as String,
        bgColor: j['bg_color'] as String,
        priceXp: (j['price_xp'] as num).toInt(),
        gender: j['gender'] as String?,
        owned: j['owned'] as bool? ?? false,
        active: j['active'] as bool? ?? false,
      );
}

class SearchLocation {
  final String semester;
  final String subjectId;
  final String subjectName;
  final String bookId;
  final String bookName;
  final String academicYear;
  final String source;
  final int page;
  final String printed;
  final int occurrences;
  final int position;
  final String chapterHeader;
  final int? chapterNumber;
  final String? chapterName;

  SearchLocation({
    required this.semester,
    required this.subjectId,
    required this.subjectName,
    required this.bookId,
    required this.bookName,
    required this.academicYear,
    required this.source,
    required this.page,
    required this.printed,
    required this.occurrences,
    required this.position,
    this.chapterHeader = '',
    this.chapterNumber,
    this.chapterName,
  });

  factory SearchLocation.fromJson(Map<String, dynamic> j) => SearchLocation(
        semester: j['semester'] as String,
        subjectId: j['subject_id'] as String,
        subjectName: j['subject_name'] as String,
        bookId: (j['book_id'] ?? '') as String,
        bookName: (j['book_name'] ?? j['subject_name']) as String,
        academicYear: (j['academic_year'] ?? '') as String,
        source: j['source'] as String,
        page: j['page'] as int,
        printed: j['printed'].toString(),
        occurrences: j['occurrences'] as int,
        position: j['position'] as int,
        chapterHeader: (j['chapter_header'] ?? '') as String,
        chapterNumber: j['chapter_number'] as int?,
        chapterName: j['chapter_name'] as String?,
      );
}

class SearchResult {
  final String query;
  final String queryId;
  final int total;
  final String? summary;
  final List<SearchLocation> locations;

  SearchResult({
    required this.query,
    required this.queryId,
    required this.total,
    required this.summary,
    required this.locations,
  });

  factory SearchResult.fromJson(Map<String, dynamic> j) => SearchResult(
        query: j['query'] as String,
        queryId: j['query_id'] as String,
        total: j['total'] as int,
        summary: j['summary'] as String?,
        locations: (j['locations'] as List)
            .map((e) => SearchLocation.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class Explanation {
  final String simple;
  final String advanced;
  final String realLife;
  final List<String> related;

  Explanation({
    required this.simple,
    required this.advanced,
    required this.realLife,
    required this.related,
  });

  factory Explanation.fromJson(Map<String, dynamic> j) => Explanation(
        simple: j['simple'] as String? ?? '',
        advanced: j['advanced'] as String? ?? '',
        realLife: j['real_life'] as String? ?? '',
        related:
            (j['related'] as List? ?? []).map((e) => e.toString()).toList(),
      );
}

class Mcq {
  final String question;
  final List<String> options;
  final int correctIndex;
  final String difficulty; // "easy" | "medium" | "hard"

  Mcq({
    required this.question,
    required this.options,
    required this.correctIndex,
    this.difficulty = 'medium',
  });

  factory Mcq.fromJson(Map<String, dynamic> j) => Mcq(
        question: j['question'] as String,
        options: (j['options'] as List).map((e) => e.toString()).toList(),
        correctIndex: j['correct_index'] as int,
        difficulty: j['difficulty'] as String? ?? 'medium',
      );
}

class UserXp {
  final int xp;
  final int level;
  final int totalChallenges;
  final int nextLevelXp;

  UserXp({
    required this.xp,
    required this.level,
    required this.totalChallenges,
    required this.nextLevelXp,
  });

  factory UserXp.fromJson(Map<String, dynamic> j) => UserXp(
        xp: j['xp'] as int,
        level: j['level'] as int,
        totalChallenges: j['total_challenges'] as int,
        nextLevelXp: j['next_level_xp'] as int,
      );
}

class ChapterInfo {
  final String key;
  final String name;
  final int? number;

  ChapterInfo({required this.key, required this.name, this.number});

  factory ChapterInfo.fromJson(Map<String, dynamic> j) => ChapterInfo(
        key: j['key'] as String,
        name: j['name'] as String,
        number: j['number'] as int?,
      );
}

class SubjectCurriculum {
  final String subjectId;
  final String nameAr;
  final List<ChapterInfo> chapters;

  SubjectCurriculum({required this.subjectId, required this.nameAr, required this.chapters});

  factory SubjectCurriculum.fromJson(Map<String, dynamic> j) => SubjectCurriculum(
        subjectId: j['subject_id'] as String,
        nameAr: (j['name_ar'] as String?) ?? j['subject_id'] as String,
        chapters: (j['chapters'] as List)
            .map((e) => ChapterInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class StudyPair {
  final int pairId;
  final int partnerId;
  final String partnerName;
  final String partnerEmail;
  final String status;
  final bool isHost;

  StudyPair({
    required this.pairId,
    required this.partnerId,
    required this.partnerName,
    required this.partnerEmail,
    required this.status,
    required this.isHost,
  });

  factory StudyPair.fromJson(Map<String, dynamic> j) => StudyPair(
        pairId: j['pair_id'] as int,
        partnerId: j['partner_id'] as int? ?? 0,
        partnerName: j['partner_name'] as String? ?? '—',
        partnerEmail: j['partner_email'] as String? ?? '',
        status: j['status'] as String,
        isHost: j['is_host'] as bool? ?? true,
      );
}

class PairProgress {
  final String name;
  final int userId;
  final List<String> done;

  PairProgress({required this.name, required this.userId, required this.done});

  factory PairProgress.fromJson(Map<String, dynamic> j) => PairProgress(
        userId: j['user_id'] as int,
        name: j['name'] as String,
        done: (j['done'] as List).map((e) => e.toString()).toList(),
      );
}

class ChallengeRoom {
  final int challengeId;
  final String type;
  final String status;
  final String subjectId;
  final String semester;
  final String? inviteCode;
  final bool isHost;
  final List<ChallengePlayerInfo> players;

  ChallengeRoom({
    required this.challengeId,
    required this.type,
    required this.status,
    required this.subjectId,
    required this.semester,
    required this.inviteCode,
    required this.isHost,
    required this.players,
  });

  factory ChallengeRoom.fromJson(Map<String, dynamic> j) => ChallengeRoom(
        challengeId: j['challenge_id'] as int,
        type: j['type'] as String,
        status: j['status'] as String,
        subjectId: j['subject_id'] as String,
        semester: j['semester'] as String,
        inviteCode: j['invite_code'] as String?,
        isHost: j['is_host'] as bool,
        players: (j['players'] as List)
            .map((e) => ChallengePlayerInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class ChallengePlayerInfo {
  final int userId;
  final String name;
  final int score;
  final int xpEarned;

  ChallengePlayerInfo({
    required this.userId,
    required this.name,
    required this.score,
    required this.xpEarned,
  });

  factory ChallengePlayerInfo.fromJson(Map<String, dynamic> j) => ChallengePlayerInfo(
        userId: j['user_id'] as int,
        name: j['name'] as String,
        score: j['score'] as int,
        xpEarned: (j['xp_earned'] ?? 0) as int,
      );
}

class OpenChallenge {
  final int challengeId;
  final String subjectId;
  final String subjectName;
  final String semester;
  final String hostName;
  final int playerCount;

  OpenChallenge({
    required this.challengeId,
    required this.subjectId,
    required this.subjectName,
    required this.semester,
    required this.hostName,
    required this.playerCount,
  });

  factory OpenChallenge.fromJson(Map<String, dynamic> j) => OpenChallenge(
        challengeId: j['challenge_id'] as int,
        subjectId: j['subject_id'] as String,
        subjectName: j['subject_name'] as String? ?? j['subject_id'] as String,
        semester: j['semester'] as String,
        hostName: j['host_name'] as String,
        playerCount: j['player_count'] as int,
      );
}

class AppNotification {
  final int id;
  final String title;
  final String body;
  final String createdAt;

  AppNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.createdAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: j['id'] as int,
        title: j['title'] as String,
        body: j['body'] as String,
        createdAt: j['created_at'] as String,
      );
}
