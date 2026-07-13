import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'page_viewer_screen.dart';

/// Results for a keyword: locations + the three AI views (summary/explain/quiz).
class SearchResultScreen extends StatelessWidget {
  final String semester;
  final SearchResult result;
  const SearchResultScreen(
      {super.key, required this.semester, required this.result});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
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
            _LocationsView(query: result.query, queryId: result.queryId,
                locations: result.locations),
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
    if (e.isRateLimited) return 'وصلت للحد اليومي للذكاء الاصطناعي. حاول لاحقاً.';
    if (e.status == 503) return 'ميزات الذكاء الاصطناعي غير مفعّلة حالياً.';
    return e.message;
  }
  return 'حدث خطأ. حاول مجدداً.';
}

// -- locations --------------------------------------------------------------
class _LocationsView extends StatelessWidget {
  final String query;
  final String queryId;
  final List<SearchLocation> locations;
  const _LocationsView(
      {required this.query, required this.queryId, required this.locations});

  @override
  Widget build(BuildContext context) {
    // Group by BOOK (a subject may have several books / academic years),
    // preserving the order books first appear in the results.
    final byBook = <String, List<SearchLocation>>{};
    for (final l in locations) {
      byBook.putIfAbsent(l.bookId.isNotEmpty ? l.bookId : l.bookName, () => []).add(l);
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        for (final group in byBook.values) ...[
          _bookHeader(context, group.first),
          ...group.map((l) => Card(
                child: ListTile(
                  leading: const Icon(Icons.description_outlined),
                  title: Text('صفحة ${l.printed}'),
                  subtitle: Text('${l.occurrences} مرة في هذه الصفحة'),
                  trailing: const Icon(Icons.chevron_left),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => PageViewerScreen(
                      query: query,
                      queryId: queryId,
                      locations: locations,
                      initialIndex: l.position,
                    ),
                  )),
                ),
              )),
        ],
      ],
    );
  }

  Widget _bookHeader(BuildContext context, SearchLocation l) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 16, 4, 6),
      child: Row(
        children: [
          Icon(Icons.menu_book_rounded, size: 20, color: scheme.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.bookName,
                    style: Theme.of(context).textTheme.titleMedium),
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
          if (l.academicYear.isNotEmpty)
            Chip(
              label: Text(l.academicYear,
                  style: const TextStyle(fontSize: 11)),
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
            ),
        ],
      ),
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
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: SectionCard(
            title: 'ملخص',
            icon: Icons.notes,
            child: SelectableText(snap.data ?? '—',
                style: const TextStyle(height: 1.6)),
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
  Future<Explanation>? _future;
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = context.read<AuthController>().api
        .explanation(widget.semester, widget.keyword);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return FutureBuilder<Explanation>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Loading();
        }
        if (snap.hasError) return ErrorView(friendlyAiError(snap.error!));
        final e = snap.data!;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionCard(title: 'ببساطة', icon: Icons.lightbulb_outline,
                child: Text(e.simple, style: const TextStyle(height: 1.6))),
            const SizedBox(height: 12),
            SectionCard(title: 'بتعمّق', icon: Icons.school_outlined,
                child: Text(e.advanced, style: const TextStyle(height: 1.6))),
            const SizedBox(height: 12),
            SectionCard(title: 'تطبيق واقعي', icon: Icons.public,
                child: Text(e.realLife, style: const TextStyle(height: 1.6))),
            const SizedBox(height: 12),
            SectionCard(
              title: 'مفاهيم مرتبطة',
              icon: Icons.link,
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children:
                    e.related.map((r) => Chip(label: Text(r))).toList(),
              ),
            ),
          ],
        );
      },
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
  bool _busy = true;
  String? _error;

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
    });
    try {
      final q = await context.read<AuthController>().api
          .questions(widget.semester, widget.keyword, refresh: refresh);
      setState(() => _questions = q);
    } catch (e) {
      setState(() => _error = friendlyAiError(e));
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
          _QuestionCard(index: i + 1, mcq: questions[i]),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => _load(refresh: true),
          icon: const Icon(Icons.refresh),
          label: const Text('توليد المزيد'),
        ),
      ],
    );
  }
}

/// A single interactive MCQ that reveals correctness on tap.
class _QuestionCard extends StatefulWidget {
  final int index;
  final Mcq mcq;
  const _QuestionCard({required this.index, required this.mcq});
  @override
  State<_QuestionCard> createState() => _QuestionCardState();
}

class _QuestionCardState extends State<_QuestionCard> {
  int? _picked;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${widget.index}. ${widget.mcq.question}',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            ...List.generate(widget.mcq.options.length, (i) {
              final isCorrect = i == widget.mcq.correctIndex;
              final isPicked = i == _picked;
              Color? bg;
              if (_picked != null) {
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
                  onTap: _picked == null
                      ? () => setState(() => _picked = i)
                      : null,
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: bg ?? scheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(children: [
                      if (_picked != null && isCorrect)
                        const Icon(Icons.check_circle,
                            color: Colors.green, size: 20)
                      else if (_picked != null && isPicked)
                        Icon(Icons.cancel, color: scheme.error, size: 20)
                      else
                        const Icon(Icons.radio_button_unchecked, size: 20),
                      const SizedBox(width: 10),
                      Expanded(child: Text(widget.mcq.options[i])),
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
