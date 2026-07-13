import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'subscription_screen.dart';

/// Profile: name, year, semester, per-subject progress, rank, update progress.
class ProfileTab extends StatefulWidget {
  final ValueNotifier<String> semester;
  const ProfileTab({super.key, required this.semester});

  @override
  State<ProfileTab> createState() => _ProfileTabState();
}

class _ProfileTabState extends State<ProfileTab> {
  Future<Profile>? _future;

  @override
  void initState() {
    super.initState();
    widget.semester.addListener(_reload);
    _reload();
  }

  @override
  void dispose() {
    widget.semester.removeListener(_reload);
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = context.read<AuthController>().api.me(widget.semester.value);
    });
  }

  Future<void> _updateProgress(SubjectProgress s) async {
    final result = await showModalBottomSheet<double>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _UpdateSheet(subject: s),
    );
    if (result == null || !mounted) return;
    final auth = context.read<AuthController>();
    try {
      await auth.api.updateProgress(
        semester: widget.semester.value,
        subjectId: s.subjectId,
        chapter: 'chapter', // single rolling chapter; refine with real chapters
        percent: result,
      );
      _reload();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('تعذّر الحفظ: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<Profile>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Loading();
          }
          if (snap.hasError) {
            return ErrorView('تعذّر تحميل الملف: ${snap.error}',
                onRetry: _reload);
          }
          final p = snap.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _header(context, p),
              const SizedBox(height: 16),
              _rankCard(context, p),
              const SizedBox(height: 16),
              Text('المواد', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              ...p.subjects.map((s) => _subjectTile(context, s)),
            ],
          );
        },
      ),
    );
  }

  Widget _header(BuildContext context, Profile p) {
    final scheme = Theme.of(context).colorScheme;
    return Row(children: [
      CircleAvatar(
          radius: 28,
          backgroundColor: scheme.primaryContainer,
          child: Text((p.name ?? p.email).characters.first.toUpperCase())),
      const SizedBox(width: 12),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(p.name ?? p.email,
              style: Theme.of(context).textTheme.titleMedium),
          Text('السنة التحضيرية',
              style: TextStyle(color: scheme.onSurfaceVariant)),
        ]),
      ),
      IconButton(
        tooltip: 'الاشتراك',
        onPressed: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => const SubscriptionScreen()))
            .then((_) => _reload()),
        icon: const Icon(Icons.card_membership),
      ),
      IconButton(
        tooltip: 'خروج',
        onPressed: () => context.read<AuthController>().logout(),
        icon: const Icon(Icons.logout),
      ),
    ]);
  }

  Widget _rankCard(BuildContext context, Profile p) {
    return SectionCard(
      title: 'ترتيبك',
      icon: Icons.emoji_events,
      child: Text(
        p.rank == null
            ? 'ابدأ بتحديث إنجازك لتظهر في الترتيب'
            : 'المرتبة ${p.rank} من ${p.totalStudents}',
        style: Theme.of(context).textTheme.titleMedium,
      ),
    );
  }

  Widget _subjectTile(BuildContext context, SubjectProgress s) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        title: Text(s.nameAr),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: s.percent / 100,
              minHeight: 8,
              backgroundColor: scheme.surfaceContainerHighest,
            ),
          ),
        ),
        trailing: s.locked
            ? const Icon(Icons.lock_outline)
            : Text('${s.percent.round()}%',
                style: Theme.of(context).textTheme.titleMedium),
        onTap: s.locked ? null : () => _updateProgress(s),
      ),
    );
  }
}

/// Bottom sheet to pick a new completion percentage for a subject.
class _UpdateSheet extends StatefulWidget {
  final SubjectProgress subject;
  const _UpdateSheet({required this.subject});

  @override
  State<_UpdateSheet> createState() => _UpdateSheetState();
}

class _UpdateSheetState extends State<_UpdateSheet> {
  late double _value = widget.subject.percent;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('تحديث إنجاز ${widget.subject.nameAr}',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text('${_value.round()}%',
            style: Theme.of(context).textTheme.headlineMedium),
        Slider(
          value: _value,
          max: 100,
          divisions: 20,
          label: '${_value.round()}%',
          onChanged: (v) => setState(() => _value = v),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _value),
          child: const Text('حفظ'),
        ),
      ]),
    );
  }
}
