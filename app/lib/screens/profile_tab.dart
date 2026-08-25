import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import '../widgets/character_widget.dart';
import 'admin_chapters_screen.dart';
import 'open_challenges_screen.dart';
import 'search_result_screen.dart';
import 'store_screen.dart';
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
  UserXp? _xp;
  WordOfDay? _wod;

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
    final auth = context.read<AuthController>();
    final future = auth.api.me(widget.semester.value, year: auth.year);
    future.then((p) {
      if (!mounted) return;
      auth.setAvailableYears(p.availableYears);
      auth.setActivatedSemesters(p.activatedSemesters);
    }).catchError((_) {});
    setState(() { _future = future; });
    final api = auth.api;
    api.myXp().then((xp) {
      if (mounted) setState(() => _xp = xp);
    }).catchError((_) {});
    api.wordOfDay(widget.semester.value).then((w) {
      if (mounted) setState(() => _wod = w);
    }).catchError((_) {});
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
            final auth = context.read<AuthController>();
            if (snap.error.toString().contains('401')) {
              auth.handleUnauthorized(snap.error!);
            }
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ErrorView('تعذّر تحميل الملف: ${snap.error}',
                    onRetry: _reload),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: () => _confirmLogout(context),
                  icon: const Icon(Icons.logout),
                  label: const Text('تسجيل الخروج'),
                ),
              ],
            );
          }
          final p = snap.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _header(context, p),
              const SizedBox(height: 12),
              if (_wod != null) _wordOfDayCard(context, _wod!),
              if (_wod != null) const SizedBox(height: 8),
              if (_xp != null) _xpCard(context, _xp!),
              const SizedBox(height: 4),
              _storeButton(context),
              const SizedBox(height: 4),
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
      GestureDetector(
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => const StoreScreen()))
            .then((_) => _reload()),
        child: Stack(clipBehavior: Clip.none, children: [
          CharacterWidget(skin: p.activeSkin, gender: p.gender, size: 56),
          Positioned(
            bottom: -2,
            right: -2,
            child: Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: scheme.primaryContainer,
                border: Border.all(color: scheme.surface, width: 1.5),
              ),
              child: Icon(Icons.edit, size: 11, color: scheme.onPrimaryContainer),
            ),
          ),
        ]),
      ),
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
        tooltip: 'إدارة الفصول',
        onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const AdminChaptersScreen())),
        icon: const Icon(Icons.admin_panel_settings_outlined),
      ),
      IconButton(
        tooltip: 'خروج',
        onPressed: () => _confirmLogout(context),
        icon: const Icon(Icons.logout),
      ),
    ]);
  }

  void _confirmLogout(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('تسجيل الخروج'),
        content: const Text('هل أنت متأكد من تسجيل الخروج؟'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('إلغاء'),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              context.read<AuthController>().logout();
            },
            child: const Text('خروج', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  Widget _xpCard(BuildContext context, UserXp xp) {
    final scheme = Theme.of(context).colorScheme;
    final progress = (xp.xp % 100) / 100.0;
    return SectionCard(
      title: 'المستوى ${xp.level}',
      icon: Icons.stars,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('${xp.xp} XP',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold)),
          const Spacer(),
          Text('${xp.nextLevelXp} XP → المستوى ${xp.level + 1}',
              style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12)),
        ]),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: LinearProgressIndicator(
            value: progress,
            minHeight: 12,
            backgroundColor: scheme.surfaceContainerHighest,
            valueColor: AlwaysStoppedAnimation(scheme.primary),
          ),
        ),
        const SizedBox(height: 4),
        Row(children: [
          const Icon(Icons.flash_on, size: 14),
          Text(' ${xp.totalChallenges} تحدّي',
              style: const TextStyle(fontSize: 12)),
          const Spacer(),
          GestureDetector(
            onTap: () => Navigator.push(context,
                MaterialPageRoute(builder: (_) => const OpenChallengesScreen())),
            child: Text('تحدّيات مفتوحة ←',
                style: TextStyle(
                    color: scheme.primary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600)),
          ),
        ]),
      ]),
    );
  }

  Future<void> _searchWord(String word, String semester) async {
    final api = context.read<AuthController>().api;
    final sem = semester;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    try {
      final result = await api.search(sem, word);
      if (!mounted) return;
      Navigator.of(context).pop(); // close loading
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => SearchResultScreen(semester: sem, result: result),
      ));
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context).pop(); // close loading
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('تعذّر البحث: $e')));
    }
  }

  Widget _wordOfDayCard(BuildContext context, WordOfDay wod) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.tertiaryContainer,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => _searchWord(wod.word, wod.semester),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(Icons.lightbulb_outline, size: 18, color: scheme.onTertiaryContainer),
              const SizedBox(width: 6),
              Text('كلمة اليوم',
                  style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: scheme.onTertiaryContainer,
                      fontSize: 13)),
              const Spacer(),
              Icon(Icons.search, size: 16, color: scheme.onTertiaryContainer.withValues(alpha: 0.6)),
            ]),
            const SizedBox(height: 8),
            Text(
              wod.word,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                color: scheme.onTertiaryContainer,
              ),
            ),
            if (wod.definition.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(wod.definition,
                  style: TextStyle(color: scheme.onTertiaryContainer, fontSize: 13)),
            ],
            if (wod.example.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('مثال: ${wod.example}',
                  style: TextStyle(
                      color: scheme.onTertiaryContainer.withValues(alpha: 0.75),
                      fontSize: 12,
                      fontStyle: FontStyle.italic)),
            ],
            const SizedBox(height: 8),
            Text('اضغط للبحث التفصيلي ←',
                style: TextStyle(
                    color: scheme.onTertiaryContainer.withValues(alpha: 0.6),
                    fontSize: 11,
                    fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
    );
  }

  Widget _storeButton(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return OutlinedButton.icon(
      onPressed: () => Navigator.of(context)
          .push(MaterialPageRoute(builder: (_) => const StoreScreen()))
          .then((_) => _reload()),
      icon: const Text('🛍️', style: TextStyle(fontSize: 16)),
      label: Text('متجر الشخصيات',
          style: TextStyle(fontWeight: FontWeight.w600, color: scheme.primary)),
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(double.infinity, 44),
        side: BorderSide(color: scheme.primary.withValues(alpha: 0.4)),
      ),
    );
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
      ),
    );
  }
}

