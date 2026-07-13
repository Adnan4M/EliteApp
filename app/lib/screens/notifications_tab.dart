import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';

/// General announcements for the preparatory year.
class NotificationsTab extends StatefulWidget {
  const NotificationsTab({super.key});
  @override
  State<NotificationsTab> createState() => _NotificationsTabState();
}

class _NotificationsTabState extends State<NotificationsTab> {
  Future<List<AppNotification>>? _future;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    setState(() {
      _future = context.read<AuthController>().api.notifications();
    });
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<List<AppNotification>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Loading();
          }
          if (snap.hasError) {
            return ErrorView('تعذّر تحميل الإشعارات', onRetry: _reload);
          }
          final items = snap.data ?? [];
          if (items.isEmpty) {
            return ListView(children: [
              const SizedBox(height: 120),
              Icon(Icons.notifications_off_outlined,
                  size: 56,
                  color: Theme.of(context).colorScheme.onSurfaceVariant),
              const SizedBox(height: 12),
              const Center(child: Text('لا توجد إشعارات حالياً')),
            ]);
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            itemBuilder: (context, i) {
              final n = items[i];
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.campaign_outlined),
                  title: Text(n.title),
                  subtitle: Text(n.body),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
