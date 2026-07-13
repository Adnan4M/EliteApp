/// Data models mirroring the backend's JSON responses.
library;

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

class Profile {
  final String? name;
  final String email;
  final String year;
  final String currentSemester;
  final List<SubjectProgress> subjects;
  final int? rank;
  final int totalStudents;

  Profile({
    required this.name,
    required this.email,
    required this.year,
    required this.currentSemester,
    required this.subjects,
    required this.rank,
    required this.totalStudents,
  });

  factory Profile.fromJson(Map<String, dynamic> j) => Profile(
        name: j['name'] as String?,
        email: j['email'] as String,
        year: j['year'] as String,
        currentSemester: j['current_semester'] as String,
        subjects: (j['subjects'] as List)
            .map((e) => SubjectProgress.fromJson(e as Map<String, dynamic>))
            .toList(),
        rank: j['rank'] as int?,
        totalStudents: j['total_students'] as int,
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

  Mcq({
    required this.question,
    required this.options,
    required this.correctIndex,
  });

  factory Mcq.fromJson(Map<String, dynamic> j) => Mcq(
        question: j['question'] as String,
        options: (j['options'] as List).map((e) => e.toString()).toList(),
        correctIndex: j['correct_index'] as int,
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
