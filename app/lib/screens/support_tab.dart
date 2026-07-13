import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../state/auth_controller.dart';

/// Technical support: opens a direct Telegram chat.
class SupportTab extends StatelessWidget {
  const SupportTab({super.key});

  Future<void> _openTelegram(BuildContext context) async {
    final api = context.read<AuthController>().api;
    try {
      final url = await api.supportUrl();
      final uri = Uri.parse(url);
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw Exception('cannot launch');
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('تعذّر فتح الدعم. حاول لاحقاً.')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.support_agent, size: 72, color: scheme.primary),
            const SizedBox(height: 16),
            Text('هل تحتاج مساعدة؟',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text('تواصل مع فريق الدعم مباشرة عبر تيليجرام.',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant)),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => _openTelegram(context),
              icon: const Icon(Icons.telegram),
              label: const Text('فتح محادثة الدعم'),
            ),
          ],
        ),
      ),
    );
  }
}
