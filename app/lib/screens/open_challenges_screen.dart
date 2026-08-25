import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'challenge_create_screen.dart';
import 'challenge_lobby_screen.dart';

/// Browse & join open Kahoot-style challenges.
class OpenChallengesScreen extends StatefulWidget {
  const OpenChallengesScreen({super.key});

  @override
  State<OpenChallengesScreen> createState() => _OpenChallengesScreenState();
}

class _OpenChallengesScreenState extends State<OpenChallengesScreen>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  Future<List<OpenChallenge>>? _future;
  List<Map<String, dynamic>> _pending = [];
  List<Map<String, dynamic>> _mine = [];
  Timer? _refreshTimer;
  String? _filterSubject;
  String? _filterSemester;

  @override
  void initState() {
    super.initState();
    final auth = context.read<AuthController>();
    _filterSemester = auth.semester;
    auth.addListener(_onSemesterChanged);
    _load();
    // Refresh every 5 seconds so newly created rooms appear automatically.
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) _load();
    });
  }

  void _onSemesterChanged() {
    final sem = context.read<AuthController>().semester;
    if (_filterSemester != sem) {
      setState(() => _filterSemester = sem);
      _load();
    }
  }

  @override
  void dispose() {
    context.read<AuthController>().removeListener(_onSemesterChanged);
    _refreshTimer?.cancel();
    super.dispose();
  }

  void _load() {
    final api = context.read<AuthController>().api;
    setState(() {
      _future = api.openChallenges(
        subjectId: _filterSubject,
        semester: _filterSemester,
      );
    });
    api.pendingChallenges().then((list) {
      if (mounted) setState(() => _pending = list);
    });
    api.myChallenges().then((list) {
      if (mounted) setState(() => _mine = list);
    });
  }

  Widget _filterChip(String label, bool selected, VoidCallback onTap) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? scheme.primary : scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          textDirection: TextDirection.rtl,
          style: TextStyle(
            fontSize: 13,
            color: selected ? scheme.onPrimary : scheme.onSurfaceVariant,
            fontWeight: selected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  Future<void> _joinByCode(BuildContext context) async {
    final ctrl = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('انضم بكود الدعوة'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          textCapitalization: TextCapitalization.characters,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z0-9]')),
            LengthLimitingTextInputFormatter(6),
          ],
          decoration: const InputDecoration(
            labelText: 'الكود (6 أحرف)',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (v) => Navigator.of(_).pop(v.trim().toUpperCase()),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(_).pop(null),
              child: const Text('إلغاء')),
          FilledButton(
              onPressed: () => Navigator.of(_).pop(ctrl.text.trim().toUpperCase()),
              child: const Text('انضم')),
        ],
      ),
    );
    if (code == null || code.length < 4 || !context.mounted) return;
    try {
      final api = context.read<AuthController>().api;
      final challengeId = await api.joinChallengeByCode(code);
      if (!context.mounted) return;
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ChallengeLobbyScreen(challengeId: challengeId, isHost: false),
      ));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('كود غير صحيح أو انتهت صلاحيته')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const ChallengeCreateScreen(type: 'open'),
        )).then((_) => _load()),
        icon: const Icon(Icons.add),
        label: const Text('تحدٍّ مفتوح جديد'),
      ),
      body: Column(
        children: [
          // Join by invite code card
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 16, 12, 4),
            child: Card(
              color: scheme.secondaryContainer,
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => _joinByCode(context),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: Row(children: [
                    Icon(Icons.vpn_key_outlined, color: scheme.onSecondaryContainer),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('انضم بكود الدعوة',
                            style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: scheme.onSecondaryContainer)),
                        Text('أدخل الكود الذي شاركه معك صديقك',
                            style: TextStyle(
                                fontSize: 12, color: scheme.onSecondaryContainer.withOpacity(0.8))),
                      ]),
                    ),
                    Icon(Icons.arrow_forward_ios, size: 16, color: scheme.onSecondaryContainer),
                  ]),
                ),
              ),
            ),
          ),
          // ── Filters ──
          Directionality(
            textDirection: TextDirection.rtl,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  const Icon(Icons.filter_list, size: 18, color: Colors.grey),
                  const SizedBox(width: 10),
                  const VerticalDivider(width: 1, thickness: 1, indent: 4, endIndent: 4),
                  const SizedBox(width: 10),
                  FutureBuilder<List<OpenChallenge>>(
                    future: _future,
                    builder: (_, snap) {
                      final subjectMap = <String, String>{};
                      for (final c in snap.data ?? []) {
                        subjectMap[c.subjectId] = c.subjectName;
                      }
                      return Row(children: [
                        _filterChip('كل المواد', _filterSubject == null, () {
                          setState(() => _filterSubject = null);
                          _load();
                        }),
                        for (final entry in subjectMap.entries) ...[
                          const SizedBox(width: 6),
                          _filterChip(entry.value, _filterSubject == entry.key, () {
                            setState(() => _filterSubject =
                                _filterSubject == entry.key ? null : entry.key);
                            _load();
                          }),
                        ],
                      ]);
                    },
                  ),
                ]),
              ),
            ),
          ),

          if (_mine.isNotEmpty) ...[
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text('غرفي المفتوحة', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
            ..._mine.map((ch) => Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Card(
                child: ListTile(
                  leading: const Icon(Icons.sports_esports),
                  title: Text(
                      (ch['subject_name'] as String?) ?? (ch['subject_id'] as String),
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text(ch['invite_code'] != null
                      ? 'كود: ${ch['invite_code']}  ·  ${ch['player_count']} لاعبين'
                      : '${ch['player_count']} لاعبين'),
                  trailing: SizedBox(
                    width: 72,
                    child: FilledButton(
                        style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 8)),
                        onPressed: () {
                          Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => ChallengeLobbyScreen(
                              challengeId: ch['challenge_id'] as int,
                              isHost: true,
                              inviteCode: ch['invite_code'] as String?,
                            ),
                          )).then((_) => _load());
                        },
                        child: const Text('ادخل'),
                    ),
                  ),
                ),
              ),
            )),
          ],
          if (_pending.isNotEmpty) ...[
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text('دُعيت للانضمام', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
            ..._pending.map((ch) => Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Card(
                color: scheme.tertiaryContainer,
                child: ListTile(
                  leading: Icon(Icons.sports_esports, color: scheme.onTertiaryContainer),
                  title: Text(
                      (ch['subject_name'] as String?) ?? (ch['subject_id'] as String),
                      style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: scheme.onTertiaryContainer)),
                  subtitle: Text('من: ${ch['host_name']}',
                      style: TextStyle(color: scheme.onTertiaryContainer.withOpacity(0.8))),
                  trailing: SizedBox(
                    width: 72,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                          backgroundColor: scheme.tertiary,
                          foregroundColor: scheme.onTertiary,
                          padding: const EdgeInsets.symmetric(horizontal: 8)),
                      onPressed: () async {
                        try {
                          final api = context.read<AuthController>().api;
                          await api.joinChallenge(ch['challenge_id'] as int,
                              inviteCode: ch['invite_code'] as String?);
                          if (!context.mounted) return;
                          Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => ChallengeLobbyScreen(
                              challengeId: ch['challenge_id'] as int,
                              isHost: false,
                            ),
                          ));
                        } catch (e) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('خطأ: $e')));
                          }
                        }
                      },
                      child: const Text('انضم'),
                    ),
                  ),
                ),
              ),
            )),
          ],
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Text('التحديات المفتوحة', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<OpenChallenge>>(
              future: _future,
              builder: (context, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Loading();
                }
                if (snap.hasError) {
                  return ErrorView('تعذّر التحميل', onRetry: _load);
                }
                final list = snap.data!;
                if (list.isEmpty) {
                  return RefreshIndicator(
                    onRefresh: () async => _load(),
                    child: ListView(children: const [
                      SizedBox(height: 60),
                      Center(
                        child: Text('لا توجد تحديات مفتوحة الآن.\nاضغط + لإنشاء تحدٍّ وادعُ زملاءك!',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: Colors.grey)),
                      ),
                    ]),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async => _load(),
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 4, 12, 80),
                    itemCount: list.length,
                    itemBuilder: (_, i) => _ChallengeTile(
                        challenge: list[i], onJoined: _load),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ChallengeTile extends StatelessWidget {
  final OpenChallenge challenge;
  final VoidCallback onJoined;

  const _ChallengeTile({required this.challenge, required this.onJoined});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: scheme.tertiaryContainer,
          child: const Icon(Icons.sports_esports),
        ),
        title: Text(challenge.subjectName,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text('المضيف: ${challenge.hostName}  ·  '
            '${challenge.playerCount} لاعبين'),
        trailing: SizedBox(
          width: 72,
          child: FilledButton(
            style: FilledButton.styleFrom(padding: EdgeInsets.zero),
            onPressed: () => _join(context),
            child: const Text('انضم'),
          ),
        ),
      ),
    );
  }

  Future<void> _join(BuildContext context) async {
    try {
      final api = context.read<AuthController>().api;
      await api.joinChallenge(challenge.challengeId);
      if (!context.mounted) return;
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ChallengeLobbyScreen(
          challengeId: challenge.challengeId,
          isHost: false,
        ),
      ));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('خطأ: $e')));
      }
    }
  }
}
