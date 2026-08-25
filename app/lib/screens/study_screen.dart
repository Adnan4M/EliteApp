import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'challenge_create_screen.dart';

/// Study-with-me screen: chapter completion grid + pair management.
class StudyTab extends StatefulWidget {
  final ValueNotifier<String> semester;
  const StudyTab({super.key, required this.semester});

  @override
  State<StudyTab> createState() => _StudyTabState();
}

class _StudyTabState extends State<StudyTab>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'تقدّمي'),
            Tab(text: 'رفيق الدراسة'),
          ],
        ),
        Expanded(
          child: TabBarView(
            controller: _tabs,
            children: [
              _MyProgressView(semester: widget.semester),
              _PairsView(semester: widget.semester),
            ],
          ),
        ),
      ],
    );
  }
}

// ─── My progress ─────────────────────────────────────────────────────────────

class _MyProgressView extends StatefulWidget {
  final ValueNotifier<String> semester;
  const _MyProgressView({required this.semester});

  @override
  State<_MyProgressView> createState() => _MyProgressViewState();
}

class _MyProgressViewState extends State<_MyProgressView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  bool _loading = true;
  String? _error;
  List<SubjectCurriculum> _curriculum = [];
  Set<String> _doneKeys = {};
  final Set<String> _expanded = {};

  @override
  void initState() {
    super.initState();
    widget.semester.addListener(_load);
    _load();
  }

  @override
  void dispose() {
    widget.semester.removeListener(_load);
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = context.read<AuthController>().api;
      final results = await Future.wait([
        api.curriculum(semester: widget.semester.value),
        api.myCompletions(),
      ]);
      if (!mounted) return;
      setState(() {
        _curriculum = results[0] as List<SubjectCurriculum>;
        _doneKeys = (results[1] as List<String>).toSet();
        _loading = false;
        // Reset expanded state when semester changes
        _expanded.clear();
      });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _toggle(String subjectId, String chKey, bool isDone) async {
    // Optimistic update — don't reload, just flip the key locally
    setState(() {
      if (isDone) {
        _doneKeys.remove(chKey);
      } else {
        _doneKeys.add(chKey);
      }
    });
    final api = context.read<AuthController>().api;
    final sem = widget.semester.value;
    try {
      if (isDone) {
        await api.unmarkChapter(sem, subjectId, chKey);
      } else {
        await api.markChapterDone(sem, subjectId, chKey);
      }
    } catch (e) {
      // Revert on failure
      setState(() {
        if (isDone) {
          _doneKeys.add(chKey);
        } else {
          _doneKeys.remove(chKey);
        }
      });
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('تعذّر الحفظ: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) return const Loading();
    if (_error != null) return ErrorView('تعذّر التحميل: $_error', onRetry: _load);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: _curriculum.map((s) => _SubjectCard(
          curriculum: s,
          doneKeys: _doneKeys,
          isExpanded: _expanded.contains(s.subjectId),
          onExpansionChanged: (open) {
            if (open) _expanded.add(s.subjectId);
            else _expanded.remove(s.subjectId);
          },
          onToggle: (chKey, isDone) => _toggle(s.subjectId, chKey, isDone),
        )).toList(),
      ),
    );
  }
}

class _SubjectCard extends StatelessWidget {
  final SubjectCurriculum curriculum;
  final Set<String> doneKeys;
  final bool isExpanded;
  final ValueChanged<bool> onExpansionChanged;
  final void Function(String chKey, bool isDone) onToggle;

  const _SubjectCard({
    required this.curriculum,
    required this.doneKeys,
    required this.isExpanded,
    required this.onExpansionChanged,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final total = curriculum.chapters.length;
    final doneCount = curriculum.chapters
        .where((c) => doneKeys.contains(c.key))
        .length;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        key: PageStorageKey(curriculum.subjectId),
        initiallyExpanded: isExpanded,
        onExpansionChanged: onExpansionChanged,
        title: Text(curriculum.nameAr,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text('$doneCount / $total فصول مكتملة',
            style: TextStyle(
                fontSize: 12,
                color: doneCount == total
                    ? scheme.primary
                    : scheme.onSurfaceVariant)),
        leading: CircleAvatar(
          backgroundColor: scheme.primaryContainer,
          child: Text('${(doneCount / total * 100).round()}%',
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: scheme.onPrimaryContainer)),
        ),
        children: curriculum.chapters.indexed.map((rec) {
          final i = rec.$1;
          final ch = rec.$2;
          final isDone = doneKeys.contains(ch.key);
          return ListTile(
            dense: true,
            leading: Text('${ch.number ?? i + 1}',
                style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontWeight: FontWeight.bold)),
            title: Text(ch.name),
            trailing: Checkbox(
              value: isDone,
              onChanged: (_) => onToggle(ch.key, isDone),
            ),
            onTap: () => onToggle(ch.key, isDone),
          );
        }).toList(),
      ),
    );
  }
}

// ─── Pairs ───────────────────────────────────────────────────────────────────

class _PairsView extends StatefulWidget {
  final ValueNotifier<String> semester;
  const _PairsView({required this.semester});

  @override
  State<_PairsView> createState() => _PairsViewState();
}

class _PairsViewState extends State<_PairsView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  Future<List<StudyPair>>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() {
      _future = context.read<AuthController>().api.myPairs();
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final scheme = Theme.of(context).colorScheme;
    return FutureBuilder<List<StudyPair>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Loading();
        }
        if (snap.hasError) {
          return ErrorView('تعذّر التحميل: ${snap.error}', onRetry: _load);
        }
        final pairs = snap.data!;
        return RefreshIndicator(
          onRefresh: () async => _load(),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // ── Action buttons ──
              Row(children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _createPair,
                    icon: const Icon(Icons.add_link),
                    label: const Text('إنشاء كود'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _joinDialog,
                    icon: const Icon(Icons.login),
                    label: const Text('أدخل كوداً'),
                  ),
                ),
              ]),
              const SizedBox(height: 16),
              if (pairs.isEmpty)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(children: [
                      Icon(Icons.group_outlined,
                          size: 64, color: scheme.onSurfaceVariant),
                      const SizedBox(height: 12),
                      const Text(
                        'لا يوجد رفاق بعد.\nأنشئ كوداً وشاركه مع صديقك،\nأو أدخل كود صديقك للانضمام.',
                        textAlign: TextAlign.center,
                      ),
                    ]),
                  ),
                ),
              ...pairs.map((p) => _PairTile(pair: p, onRefresh: _load, semester: widget.semester.value)),
            ],
          ),
        );
      },
    );
  }

  Future<void> _createPair() async {
    final api = context.read<AuthController>().api;
    try {
      final result = await api.createPair();
      if (!mounted) return;
      final code = result['invite_code'] as String;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('كود الدعوة'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text('شارك هذا الكود مع صديقك:',
                textAlign: TextAlign.center),
            const SizedBox(height: 16),
            Tooltip(
              message: 'اضغط للنسخ',
              child: GestureDetector(
                onTap: () {
                  Clipboard.setData(ClipboardData(text: code));
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('✓ تم نسخ الكود')),
                  );
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                  decoration: BoxDecoration(
                    color: Theme.of(ctx).colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Text(
                      code,
                      style: TextStyle(
                        fontSize: 36,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 10,
                        color: Theme.of(ctx).colorScheme.onPrimaryContainer,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Icon(Icons.copy, size: 20,
                        color: Theme.of(ctx).colorScheme.onPrimaryContainer),
                  ]),
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Text('اضغط على الكود لنسخه',
                style: TextStyle(fontSize: 12)),
          ]),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('تم'),
            ),
          ],
        ),
      );
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('خطأ: $e')));
      }
    }
  }

  Future<void> _joinDialog() async {
    final ctrl = TextEditingController();
    final api = context.read<AuthController>().api;
    final messenger = ScaffoldMessenger.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('أدخل كود الدعوة'),
        content: TextField(
          controller: ctrl,
          decoration: const InputDecoration(
            labelText: 'الكود (6 أحرف)',
            border: OutlineInputBorder(),
          ),
          textCapitalization: TextCapitalization.characters,
          maxLength: 6,
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('إلغاء')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('انضم')),
        ],
      ),
    );
    if (ok != true || ctrl.text.trim().isEmpty) return;
    try {
      final result = await api.joinPair(ctrl.text.trim().toUpperCase());
      if (mounted) {
        messenger.showSnackBar(SnackBar(
            content:
                Text('انضممت إلى ${result['partner_name'] ?? 'رفيقك'}!')));
        _load();
      }
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('خطأ: $e')));
      }
    }
  }
}

class _PairTile extends StatelessWidget {
  final StudyPair pair;
  final VoidCallback onRefresh;
  final String semester;

  const _PairTile({required this.pair, required this.onRefresh, required this.semester});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isActive = pair.status == 'active';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: scheme.secondaryContainer,
          child: Text(pair.partnerName.characters.first.toUpperCase()),
        ),
        title: Text(pair.partnerName),
        subtitle: Text(isActive ? 'نشط' : 'في انتظار الانضمام'),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          if (isActive) const Icon(Icons.check_circle, color: Colors.green)
          else const Icon(Icons.schedule, color: Colors.orange),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.person_remove_outlined, color: Colors.red),
            tooltip: 'مغادرة',
            onPressed: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (_) => AlertDialog(
                  title: const Text('مغادرة الزوج'),
                  content: const Text('هل تريد مغادرة هذا الزوج الدراسي؟'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(context, false),
                        child: const Text('إلغاء')),
                    FilledButton(
                      style: FilledButton.styleFrom(backgroundColor: Colors.red),
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('مغادرة'),
                    ),
                  ],
                ),
              );
              if (confirm == true) {
                await context.read<AuthController>().api.leavePair(pair.pairId);
                onRefresh();
              }
            },
          ),
        ]),
        onTap: isActive
            ? () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => _PairProgressScreen(
                      pair: pair, semester: semester),
                ))
            : null,
      ),
    );
  }
}

// ─── Pair progress detail ─────────────────────────────────────────────────────

class _PairProgressScreen extends StatefulWidget {
  final StudyPair pair;
  final String semester;
  const _PairProgressScreen({required this.pair, required this.semester});

  @override
  State<_PairProgressScreen> createState() => _PairProgressScreenState();
}

class _PairProgressScreenState extends State<_PairProgressScreen> {
  bool _loading = true;
  String? _error;
  List<SubjectCurriculum> _curriculum = [];
  PairProgress? _me;
  PairProgress? _partner;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = context.read<AuthController>().api;
      final results = await Future.wait([
        api.curriculum(semester: widget.semester),
        api.pairProgress(widget.pair.pairId),
      ]);
      final curriculum = results[0] as List<SubjectCurriculum>;
      final prog = results[1] as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _curriculum = curriculum;
        _me = PairProgress.fromJson(prog['me'] as Map<String, dynamic>);
        _partner = PairProgress.fromJson(prog['partner'] as Map<String, dynamic>);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('مع ${widget.pair.partnerName}')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text('خطأ: $_error', style: const TextStyle(color: Colors.red),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: _load, child: const Text('إعادة المحاولة')),
                ]))
              : _curriculum.isEmpty
                  ? const Center(
                      child: Text('لم يتم إضافة الفصول الدراسية بعد.',
                          style: TextStyle(color: Colors.grey)))
                  : ListView(
                      padding: const EdgeInsets.all(12),
                      children: [
                        Row(children: [
                          _legend(context, Colors.green, 'أنت'),
                          const SizedBox(width: 16),
                          _legend(context, Colors.blue, _partner?.name ?? ''),
                          const SizedBox(width: 16),
                          _legend(context, Colors.orange, 'كلاكما'),
                        ]),
                        const SizedBox(height: 12),
                        ..._curriculum.map((s) => _PairSubjectCard(
                              curriculum: s,
                              meDone: _me?.done.toSet() ?? {},
                              partnerDone: _partner?.done.toSet() ?? {},
                              onChallengeAll: (chs) => _launchChallenge(s, chs),
                            )),
                      ],
                    ),
    );
  }

  Widget _legend(BuildContext context, Color color, String label) {
    return Row(children: [
      Container(width: 12, height: 12,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
      const SizedBox(width: 4),
      Text(label, style: const TextStyle(fontSize: 12)),
    ]);
  }

  void _launchChallenge(SubjectCurriculum s, List<String> chapters) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChallengeCreateScreen(
        subjectId: s.subjectId,
        subjectName: s.nameAr,
        preselectedChapters: chapters,
        type: 'pair',
        partnerId: _partner?.userId,
      ),
    ));
  }
}

class _PairSubjectCard extends StatelessWidget {
  final SubjectCurriculum curriculum;
  final Set<String> meDone;
  final Set<String> partnerDone;
  final void Function(List<String> chapters) onChallengeAll;

  const _PairSubjectCard({
    required this.curriculum,
    required this.meDone,
    required this.partnerDone,
    required this.onChallengeAll,
  });

  @override
  Widget build(BuildContext context) {
    // Chapters both have completed → can challenge
    final bothDone = curriculum.chapters
        .where((c) => meDone.contains(c.key) && partnerDone.contains(c.key))
        .map((c) => c.key)
        .toList();

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(curriculum.nameAr,
                    style: const TextStyle(fontWeight: FontWeight.bold)),
                if (bothDone.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 130),
                      child: FilledButton.icon(
                        onPressed: () => onChallengeAll(bothDone),
                        icon: const Icon(Icons.sports_esports, size: 16),
                        label: const Text('تحدَّيا', style: TextStyle(fontSize: 12)),
                        style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 6)),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          ...curriculum.chapters.indexed.map((rec) {
            final i = rec.$1;
            final ch = rec.$2;
            final meHas = meDone.contains(ch.key);
            final partnerHas = partnerDone.contains(ch.key);
            Color dotColor;
            if (meHas && partnerHas) {
              dotColor = Colors.orange;
            } else if (meHas) {
              dotColor = Colors.green;
            } else if (partnerHas) {
              dotColor = Colors.blue;
            } else {
              dotColor = Colors.grey.shade300;
            }
            return ListTile(
              dense: true,
              leading: Row(mainAxisSize: MainAxisSize.min, children: [
                Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                        color: dotColor, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Text('${ch.number ?? i + 1}',
                    style: const TextStyle(fontSize: 12, color: Colors.grey)),
              ]),
              title: Text(ch.name),
            );
          }),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}
