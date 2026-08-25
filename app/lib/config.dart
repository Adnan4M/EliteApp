/// App-wide configuration.
class Config {
  /// Backend base URL.
  static const String apiBase = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'https://elite-production-6ce0.up.railway.app',
  );

  /// Fallback year used before the profile has loaded.
  static const String defaultYear = 'prep';

  /// Offline label lookup ONLY — never use this as the list of years to show.
  ///
  /// Which years exist is decided by the backend and delivered as
  /// `Profile.availableYears` (see `AuthController.availableYears`). A year
  /// listed here is not necessarily released; rendering from this map would
  /// expose years the admin has not populated yet.
  static const Map<String, String> yearLabels = {
    'prep':  'السنة التحضيرية',
    'year1': 'السنة الأولى',
    'year2': 'السنة الثانية',
    'year3': 'السنة الثالثة',
    'year4': 'السنة الرابعة',
    'year5': 'السنة الخامسة',
    'year6': 'السنة السادسة',
  };

  static const List<Semester> semesters = [
    Semester(id: 'first',  labelAr: 'الفصل الأول'),
    Semester(id: 'second', labelAr: 'الفصل الثاني'),
  ];

  static String yearLabel(String yearId) => yearLabels[yearId] ?? yearId;
}

class AcademicYear {
  final String id;
  final String labelAr;
  const AcademicYear({required this.id, required this.labelAr});
}

class Semester {
  final String id;
  final String labelAr;
  const Semester({required this.id, required this.labelAr});
}
