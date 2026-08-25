import 'package:flutter/material.dart';

import '../screens/open_challenges_screen.dart';

/// Final leaderboard + XP earned after a challenge finishes.
class ChallengeResultScreen extends StatelessWidget {
  final List<Map<String, dynamic>> leaderboard;
  final Map<String, int> xpAwards;

  const ChallengeResultScreen({
    super.key,
    required this.leaderboard,
    required this.xpAwards,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final winner = leaderboard.isNotEmpty ? leaderboard[0] : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('النتائج'),
        automaticallyImplyLeading: false,
      ),
      body: Column(
        children: [
          // Trophy header
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(24),
            color: scheme.primaryContainer,
            child: Column(children: [
              const Text('🏆', style: TextStyle(fontSize: 48)),
              if (winner != null) ...[
                const SizedBox(height: 8),
                Text(
                  winner['name'] as String,
                  style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: scheme.onPrimaryContainer),
                ),
                Text(
                  '${winner['score']} نقطة',
                  style: TextStyle(color: scheme.onPrimaryContainer),
                ),
              ],
            ]),
          ),

          // Leaderboard
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: leaderboard.length,
              itemBuilder: (_, i) {
                final p = leaderboard[i];
                final uid = p['user_id'].toString();
                final xp = xpAwards[uid] ?? 0;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: i == 0
                          ? Colors.amber
                          : i == 1
                              ? Colors.grey.shade400
                              : i == 2
                                  ? Colors.brown.shade300
                                  : scheme.surfaceContainerHighest,
                      child: Text('${i + 1}'),
                    ),
                    title: Text(p['name'] as String),
                    subtitle: Text('${p['score']} نقطة'),
                    trailing: xp > 0
                        ? Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 4),
                            decoration: BoxDecoration(
                              color: scheme.secondaryContainer,
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text('+$xp XP',
                                style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: scheme.onSecondaryContainer)),
                          )
                        : null,
                  ),
                );
              },
            ),
          ),

          // Actions
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(
                        builder: (_) => const OpenChallengesScreen()),
                    (r) => r.isFirst,
                  ),
                  child: const Text('التحديات المفتوحة'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: () => Navigator.of(context).popUntil(
                    (r) => r.isFirst,
                  ),
                  child: const Text('الرئيسية'),
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}
