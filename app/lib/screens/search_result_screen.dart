import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'page_viewer_screen.dart';

/// Renders a markdown-formatted string as a Widget, line by line.
/// Supported: ### heading, **bold**, *italic*, _underline_, ==highlight==
Widget buildMarkdown(String text, {Color? highlightColor, TextStyle? baseStyle}) {
  final lines = text.split('\n');
  final widgets = <Widget>[];
  for (final raw in lines) {
    final line = raw.trimRight();
    // Heading: ### ... (strip leading #s and space)
    final headingMatch = RegExp(r'^#{1,4}\s+(.+)$').firstMatch(line);
    if (headingMatch != null) {
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 12, bottom: 4),
        child: Text(
          headingMatch.group(1)!,
          style: (baseStyle ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
            fontSize: 15,
          ),
          textDirection: TextDirection.rtl,
        ),
      ));
      continue;
    }
    // Horizontal rule
    if (line == '---' || line == '***') {
      widgets.add(const Divider(height: 20));
      continue;
    }
    // Normal line with inline markers
    final span = _parseInline(line, highlightColor: highlightColor, baseStyle: baseStyle);
    if (span.children?.isNotEmpty == true || (span.text?.isNotEmpty == true)) {
      widgets.add(Text.rich(span,
          style: (baseStyle ?? const TextStyle()).copyWith(height: 1.8),
          textDirection: TextDirection.rtl));
    } else {
      widgets.add(const SizedBox(height: 6));
    }
  }
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: widgets,
  );
}

/// Parses inline markdown markers into a TextSpan.
/// Supported: **bold**, *italic*, _underline_, ==highlight==
TextSpan _parseInline(String text, {Color? highlightColor, TextStyle? baseStyle}) {
  final spans = <TextSpan>[];
  final pattern = RegExp(r'\*\*(.+?)\*\*|\*(.+?)\*|_(.+?)_|==(.+?)==');
  int last = 0;
  for (final m in pattern.allMatches(text)) {
    if (m.start > last) {
      spans.add(TextSpan(text: text.substring(last, m.start), style: baseStyle));
    }
    if (m.group(1) != null) {
      spans.add(TextSpan(
        text: m.group(1),
        style: (baseStyle ?? const TextStyle()).copyWith(fontWeight: FontWeight.bold),
      ));
    } else if (m.group(2) != null) {
      spans.add(TextSpan(
        text: m.group(2),
        style: (baseStyle ?? const TextStyle()).copyWith(fontStyle: FontStyle.italic),
      ));
    } else if (m.group(3) != null) {
      spans.add(TextSpan(
        text: m.group(3),
        style: (baseStyle ?? const TextStyle()).copyWith(decoration: TextDecoration.underline),
      ));
    } else if (m.group(4) != null) {
      spans.add(TextSpan(
        text: m.group(4),
        style: (baseStyle ?? const TextStyle()).copyWith(
          backgroundColor: highlightColor ?? const Color(0xFFFFEB3B).withValues(alpha: 0.4),
          fontWeight: FontWeight.w600,
        ),
      ));
    }
    last = m.end;
  }
  if (last < text.length) {
    spans.add(TextSpan(text: text.substring(last), style: baseStyle));
  }
  return TextSpan(children: spans);
}

/// Results for a keyword: locations + the three AI views (summary/explain/quiz).
class SearchResultScreen extends StatelessWidget {
  final String semester;
  final SearchResult result;
  /// 0=المواضع 1=ملخص 2=شرح 3=أسئلة
  final int initialTab;
  const SearchResultScreen({
    super.key,
    required this.semester,
    required this.result,
    this.initialTab = 0,
  });

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      initialIndex: initialTab,
      child: Scaffold(
        appBar: AppBar(
          title: Text('«${result.query}»'),
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'المواضع'),
              Tab(text: 'ملخص'),
              Tab(text: 'شرح'),
              Tab(text: 'أسئلة'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _LocationsView(query: result.query, locations: result.locations),
            _SummaryView(semester: semester, keyword: result.query),
            _ExplanationView(semester: semester, keyword: result.query),
            _QuestionsView(semester: semester, keyword: result.query),
          ],
        ),
      ),
    );
  }
}

String friendlyAiError(Object e) {
  if (e is ApiException) {
    if (e.isNotScientific) return 'not_scientific';
    if (e.isRateLimited) return 'وصلت للحد اليومي للذكاء الاصطناعي. حاول لاحقاً.';
    if (e.status == 503) return 'ميزات الذكاء الاصطناعي غير مفعّلة حالياً.';
    return e.message;
  }
  return 'حدث خطأ. حاول مجدداً.';
}

// -- locations --------------------------------------------------------------
class _LocationsView extends StatefulWidget {
  final String query;
  final List<SearchLocation> locations;
  const _LocationsView({required this.query, required this.locations});
  @override
  State<_LocationsView> createState() => _LocationsViewState();
}

class _LocationsViewState extends State<_LocationsView> {
  // Tracks which book groups are expanded; all collapsed by default.
  final Set<String> _expanded = {};

  @override
  Widget build(BuildContext context) {
    final byBook = <String, List<SearchLocation>>{};
    for (final l in widget.locations) {
      byBook.putIfAbsent(l.bookId.isNotEmpty ? l.bookId : l.bookName, () => []).add(l);
    }
    for (final pages in byBook.values) {
      pages.sort((a, b) => a.page.compareTo(b.page));
    }

    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        for (final entry in byBook.entries) ...[
          _BookGroup(
            key: ValueKey(entry.key),
            bookKey: entry.key,
            pages: entry.value,
            expanded: _expanded.contains(entry.key),
            onToggle: () => setState(() {
              if (_expanded.contains(entry.key)) {
                _expanded.remove(entry.key);
              } else {
                _expanded.add(entry.key);
              }
            }),
            query: widget.query,
            allLocations: widget.locations,
          ),
        ],
      ],
    );
  }
}

class _BookGroup extends StatelessWidget {
  final String bookKey;
  final List<SearchLocation> pages;
  final bool expanded;
  final VoidCallback onToggle;
  final String query;
  final List<SearchLocation> allLocations;

  const _BookGroup({
    super.key,
    required this.bookKey,
    required this.pages,
    required this.expanded,
    required this.onToggle,
    required this.query,
    required this.allLocations,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final l = pages.first;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ---- Collapsible book header ----
        InkWell(
          onTap: onToggle,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            margin: const EdgeInsets.only(top: 12, bottom: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: expanded ? scheme.primary.withValues(alpha: 0.5) : Colors.transparent,
              ),
            ),
            child: Row(
              children: [
                Icon(Icons.menu_book_rounded,
                    size: 22, color: scheme.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l.bookName,
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.bold)),
                      Text(
                        l.academicYear.isNotEmpty
                            ? '${l.subjectName} · ${l.academicYear}'
                            : l.subjectName,
                        style: TextStyle(
                            fontSize: 12, color: scheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                // Page count badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: scheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '${pages.length} ${pages.length == 1 ? 'صفحة' : 'صفحات'}',
                    style: TextStyle(
                        fontSize: 11,
                        color: scheme.primary,
                        fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 6),
                AnimatedRotation(
                  turns: expanded ? 0.5 : 0,
                  duration: const Duration(milliseconds: 200),
                  child: Icon(Icons.keyboard_arrow_down,
                      color: scheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        ),

        // ---- Pages list grouped by chapter (shown when expanded) ----
        AnimatedSize(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeInOut,
          child: expanded
              ? _ChapterGroups(
                  pages: pages,
                  query: query,
                  allLocations: allLocations,
                )
              : const SizedBox.shrink(),
        ),
      ],
    );
  }
}

// ─── Chapter sub-grouping inside a book ─────────────────────────────────────

class _ChapterGroups extends StatefulWidget {
  final List<SearchLocation> pages;
  final String query;
  final List<SearchLocation> allLocations;

  const _ChapterGroups({
    required this.pages,
    required this.query,
    required this.allLocations,
  });

  @override
  State<_ChapterGroups> createState() => _ChapterGroupsState();
}

class _ChapterGroupsState extends State<_ChapterGroups> {
  final Set<String> _expanded = {};

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    // Detect whether any page in this book has admin chapter data.
    final hasAnyChapter = widget.pages.any((p) => p.chapterName?.isNotEmpty == true);

    // Group pages by admin chapter name.
    // If no chapter data exists at all, use a single group '—' so pages show directly.
    final byChapter = <String, List<SearchLocation>>{};
    for (final p in widget.pages) {
      final key = p.chapterName?.isNotEmpty == true
          ? '__ch__${p.chapterNumber ?? 0}__${p.chapterName}'
          : '—';
      byChapter.putIfAbsent(key, () => []).add(p);
    }

    final widgets = <Widget>[];
    for (final entry in byChapter.entries) {
      final chKey = entry.key;
      final chPages = entry.value;
      final first = chPages.first;

      // Resolve admin chapter label (never show raw OCR text).
      String? displayLabel;
      if (chKey != '—' && first.chapterName?.isNotEmpty == true) {
        final num = first.chapterNumber;
        displayLabel = num != null
            ? 'الفصل $num — ${first.chapterName}'
            : first.chapterName!;
      }

      final isExpanded = _expanded.contains(chKey);

      if (displayLabel != null) {
        // Collapsible chapter header
        widgets.add(InkWell(
          onTap: () => setState(() {
            if (isExpanded) _expanded.remove(chKey); else _expanded.add(chKey);
          }),
          borderRadius: BorderRadius.circular(8),
          child: Container(
            margin: const EdgeInsets.only(top: 8, bottom: 2),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(8),
              border: Border(
                right: BorderSide(color: scheme.primary, width: 3),
              ),
            ),
            child: Row(children: [
              AnimatedRotation(
                turns: isExpanded ? 0.5 : 0,
                duration: const Duration(milliseconds: 200),
                child: Icon(Icons.keyboard_arrow_down,
                    size: 18, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  displayLabel,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: scheme.onSurface,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: scheme.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '${chPages.length} ${chPages.length == 1 ? 'صفحة' : 'صفحات'}',
                  style: TextStyle(fontSize: 11, color: scheme.primary),
                ),
              ),
            ]),
          ),
        ));

        widgets.add(AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeInOut,
          child: isExpanded
              ? _PageList(pages: chPages, query: widget.query,
                  allLocations: widget.allLocations)
              : const SizedBox.shrink(),
        ));
      } else if (!hasAnyChapter) {
        // Subject has no chapter data at all — show pages directly without header.
        widgets.add(_PageList(pages: chPages, query: widget.query,
            allLocations: widget.allLocations));
      }
      // else: subject has chapters but this page falls outside all ranges — skip it.
    }

    return Column(children: widgets);
  }
}

class _PageList extends StatelessWidget {
  final List<SearchLocation> pages;
  final String query;
  final List<SearchLocation> allLocations;

  const _PageList({
    required this.pages,
    required this.query,
    required this.allLocations,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: pages.map((p) => Card(
        margin: const EdgeInsets.only(bottom: 6, top: 2),
        child: ListTile(
          leading: const Icon(Icons.description_outlined),
          title: Text('صفحة ${p.printed}'),
          subtitle: Text('${p.occurrences} مرة في هذه الصفحة'),
          trailing: const Icon(Icons.chevron_left),
          onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => PageViewerScreen(
              query: query,
              locations: allLocations,
              initialIndex: allLocations.indexOf(p),
            ),
          )),
        ),
      )).toList(),
    );
  }
}

// -- summary ----------------------------------------------------------------
class _SummaryView extends StatefulWidget {
  final String semester;
  final String keyword;
  const _SummaryView({required this.semester, required this.keyword});
  @override
  State<_SummaryView> createState() => _SummaryViewState();
}

class _SummaryViewState extends State<_SummaryView>
    with AutomaticKeepAliveClientMixin {
  Future<String>? _future;
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = context.read<AuthController>().api
        .summary(widget.semester, widget.keyword);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return FutureBuilder<String>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Loading();
        }
        if (snap.hasError) {
          return ErrorView(friendlyAiError(snap.error!));
        }
        final scheme = Theme.of(context).colorScheme;
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: SectionCard(
            title: 'ملخص',
            icon: Icons.notes,
            child: buildMarkdown(
              snap.data ?? '—',
              highlightColor: scheme.primary.withValues(alpha: 0.2),
            ),
          ),
        );
      },
    );
  }
}

// -- explanation ------------------------------------------------------------
class _ExplanationView extends StatefulWidget {
  final String semester;
  final String keyword;
  const _ExplanationView({required this.semester, required this.keyword});
  @override
  State<_ExplanationView> createState() => _ExplanationViewState();
}

class _ExplanationViewState extends State<_ExplanationView>
    with AutomaticKeepAliveClientMixin {
  Explanation? _aiData;
  bool _aiLoading = true;
  String? _aiError;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _fetchAI();
  }

  void _openRelated(String keyword) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _RelatedExplanationPage(
        semester: widget.semester,
        keyword: keyword,
      ),
    ));
  }

  Future<void> _fetchAI() async {
    setState(() {
      _aiLoading = true;
      _aiError = null;
    });
    try {
      final e = await context.read<AuthController>().api
          .explanation(widget.semester, widget.keyword);
      if (mounted) setState(() => _aiData = e);
    } catch (e) {
      if (mounted) setState(() => _aiError = friendlyAiError(e));
    } finally {
      if (mounted) setState(() => _aiLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_aiLoading) return const Loading();

    if (_aiError == 'not_scientific') {
      return _NotScientificView(keyword: widget.keyword);
    }

    if (_aiError != null) {
      return ErrorView(_aiError!, onRetry: _fetchAI);
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_aiData != null) ...[
          SectionCard(
            title: 'شرح الذكاء الاصطناعي',
            icon: Icons.auto_awesome,
            child: buildMarkdown(_aiData!.simple),
          ),
          if (_aiData!.realLife.isNotEmpty) ...[
            const SizedBox(height: 12),
            SectionCard(
              title: 'تطبيق واقعي',
              icon: Icons.local_hospital_outlined,
              child: buildMarkdown(_aiData!.realLife),
            ),
          ],
          if (_aiData!.related.isNotEmpty) ...[
            const SizedBox(height: 12),
            SectionCard(
              title: 'مفاهيم مرتبطة',
              icon: Icons.link,
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _aiData!.related.map((r) => ActionChip(
                  label: Text(r),
                  avatar: const Icon(Icons.search, size: 16),
                  onPressed: () => _openRelated(r),
                )).toList(),
              ),
            ),
          ],
        ],
        const SizedBox(height: 16),
      ],
    );
  }
}

// -- questions --------------------------------------------------------------
class _QuestionsView extends StatefulWidget {
  final String semester;
  final String keyword;
  const _QuestionsView({required this.semester, required this.keyword});
  @override
  State<_QuestionsView> createState() => _QuestionsViewState();
}

class _QuestionsViewState extends State<_QuestionsView>
    with AutomaticKeepAliveClientMixin {
  List<Mcq>? _questions;
  bool _busy = false;
  String? _error;
  final Map<int, int> _picked = {};

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool refresh = false}) async {
    setState(() {
      _busy = true;
      _error = null;
      if (refresh) _picked.clear();
    });
    try {
      final q = await context.read<AuthController>().api
          .questions(widget.semester, widget.keyword, refresh: refresh);
      if (mounted) setState(() => _questions = q);
    } catch (e) {
      if (mounted) setState(() => _error = friendlyAiError(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_busy) return const Loading();

    if (_error != null) {
      return ErrorView(_error!, onRetry: () => _load());
    }

    final questions = _questions ?? [];
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (var i = 0; i < questions.length; i++)
          _QuestionCard(
            index: i + 1,
            mcq: questions[i],
            picked: _picked[i],
            onPick: (v) => setState(() => _picked[i] = v),
          ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => _load(refresh: true),
          icon: const Icon(Icons.auto_awesome),
          label: const Text('توليد أسئلة جديدة'),
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}

/// A single interactive MCQ that reveals correctness on tap.
class _QuestionCard extends StatelessWidget {
  final int index;
  final Mcq mcq;
  final int? picked;
  final ValueChanged<int> onPick;

  const _QuestionCard({
    required this.index,
    required this.mcq,
    required this.picked,
    required this.onPick,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text('$index. ${mcq.question}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                const SizedBox(width: 8),
                _DifficultyBadge(difficulty: mcq.difficulty),
              ],
            ),
            const SizedBox(height: 12),
            ...List.generate(mcq.options.length, (i) {
              final isCorrect = i == mcq.correctIndex;
              final isPicked = i == picked;
              Color? bg;
              if (picked != null) {
                if (isCorrect) {
                  bg = Colors.green.withValues(alpha: 0.18);
                } else if (isPicked) {
                  bg = scheme.error.withValues(alpha: 0.15);
                }
              }
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: picked == null ? () => onPick(i) : null,
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: bg ?? scheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(children: [
                      if (picked != null && isCorrect)
                        const Icon(Icons.check_circle,
                            color: Colors.green, size: 20)
                      else if (picked != null && isPicked)
                        Icon(Icons.cancel, color: scheme.error, size: 20)
                      else
                        const Icon(Icons.radio_button_unchecked, size: 20),
                      const SizedBox(width: 10),
                      Expanded(child: Text(mcq.options[i])),
                    ]),
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

// ─── AI-only explanation for related terms not found in the book ──────────────

// ─── Difficulty badge ────────────────────────────────────────────────────────

class _DifficultyBadge extends StatelessWidget {
  final String difficulty;
  const _DifficultyBadge({required this.difficulty});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (difficulty) {
      'easy'  => ('سهل',   const Color(0xFF16A34A)),
      'hard'  => ('صعب',   const Color(0xFFDC2626)),
      _       => ('متوسط', const Color(0xFFD97706)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}

// ─── Shown when AI detects the query is not a scientific term ────────────────

class _NotScientificView extends StatelessWidget {
  final String keyword;
  const _NotScientificView({required this.keyword});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.science_outlined, size: 64,
                color: scheme.error.withValues(alpha: 0.6)),
            const SizedBox(height: 16),
            Text(
              '«$keyword»',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 10),
            Text(
              'هذا ليس مصطلحاً علمياً أو طبياً.\nيُسمح بالبحث عن المصطلحات الطبية والعلمية فقط.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _RelatedExplanationPage extends StatefulWidget {
  final String semester;
  final String keyword;
  const _RelatedExplanationPage(
      {required this.semester, required this.keyword});

  @override
  State<_RelatedExplanationPage> createState() =>
      _RelatedExplanationPageState();
}

class _RelatedExplanationPageState extends State<_RelatedExplanationPage> {
  String? _bookText;      // null = loading, '' = not found
  Explanation? _aiData;
  bool _bookLoading = true;
  bool _aiLoading = true;
  String? _aiError;

  @override
  void initState() {
    super.initState();
    _loadBook();
    _loadAI();
  }

  Future<void> _loadBook() async {
    try {
      final text = await context
          .read<AuthController>()
          .api
          .summary(widget.semester, widget.keyword);
      if (mounted) setState(() => _bookText = text);
    } catch (_) {
      if (mounted) setState(() => _bookText = '');
    } finally {
      if (mounted) setState(() => _bookLoading = false);
    }
  }

  Future<void> _loadAI() async {
    try {
      final e = await context
          .read<AuthController>()
          .api
          .explanation(widget.semester, widget.keyword);
      if (mounted) setState(() => _aiData = e);
    } catch (e) {
      if (mounted) setState(() => _aiError = friendlyAiError(e));
    } finally {
      if (mounted) setState(() => _aiLoading = false);
    }
  }

  void _openRelated(String keyword) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _RelatedExplanationPage(
        semester: widget.semester,
        keyword: keyword,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final bookEmpty = _bookText == null || _bookText!.trim().isEmpty;

    return Scaffold(
      appBar: AppBar(title: Text('«${widget.keyword}»')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Book text section ──
          if (_bookLoading)
            const Center(child: Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: CircularProgressIndicator(),
            ))
          else if (!bookEmpty)
            SectionCard(
              title: 'من الكتاب',
              icon: Icons.menu_book_rounded,
              child: buildMarkdown(_bookText!),
            )
          else
            Card(
              color: scheme.secondaryContainer.withValues(alpha: 0.4),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(children: [
                  Icon(Icons.info_outline, size: 18, color: scheme.secondary),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'هذا المصطلح غير موجود في الكتاب — الشرح أدناه من الذكاء الاصطناعي.',
                      style: TextStyle(fontSize: 13),
                    ),
                  ),
                ]),
              ),
            ),

          const SizedBox(height: 12),

          // ── AI explanation section ──
          if (_aiLoading)
            const Center(child: Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: CircularProgressIndicator(),
            ))
          else if (_aiError == 'not_scientific')
            _NotScientificView(keyword: widget.keyword)
          else if (_aiError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(_aiError!, style: const TextStyle(color: Colors.red),
                  textAlign: TextAlign.center),
            )
          else if (_aiData != null) ...[
            SectionCard(
              title: 'شرح الذكاء الاصطناعي',
              icon: Icons.auto_awesome,
              child: buildMarkdown(_aiData!.simple),
            ),
            if (_aiData!.realLife.isNotEmpty) ...[
              const SizedBox(height: 12),
              SectionCard(
                title: 'تطبيق واقعي',
                icon: Icons.local_hospital_outlined,
                child: buildMarkdown(_aiData!.realLife),
              ),
            ],
            if (_aiData!.related.isNotEmpty) ...[
              const SizedBox(height: 12),
              SectionCard(
                title: 'مفاهيم مرتبطة',
                icon: Icons.link,
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: _aiData!.related
                      .map((r) => ActionChip(
                            label: Text(r),
                            avatar: const Icon(Icons.search, size: 16),
                            onPressed: () => _openRelated(r),
                          ))
                      .toList(),
                ),
              ),
            ],
          ],
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
