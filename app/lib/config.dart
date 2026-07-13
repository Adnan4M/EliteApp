/// App-wide configuration.
class Config {
  /// Backend base URL.
  ///
  /// - Android emulator reaches the host machine at 10.0.2.2.
  /// - iOS simulator / desktop can use localhost.
  /// Override at build time with: --dart-define=API_BASE=https://api.example.com
  static const String apiBase = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// The only year this app serves.
  static const String yearLabel = 'السنة التحضيرية';

  static const List<Semester> semesters = [
    Semester(id: 'first', labelAr: 'الفصل الأول'),
    Semester(id: 'second', labelAr: 'الفصل الثاني'),
  ];
}

class Semester {
  final String id;
  final String labelAr;
  const Semester({required this.id, required this.labelAr});
}
