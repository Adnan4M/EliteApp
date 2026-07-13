import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config.dart';
import '../state/auth_controller.dart';

/// Redeem a per-semester activation code (no full-year subscription).
class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key});
  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _message;
  bool _success = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _redeem() async {
    final code = _code.text.trim();
    if (code.isEmpty) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await context.read<AuthController>().api.redeemCode(code);
      setState(() {
        _success = true;
        _message = 'تم التفعيل بنجاح ✅';
      });
    } catch (e) {
      final s = e.toString();
      setState(() {
        _success = false;
        _message = s.contains('404')
            ? 'الرمز غير موجود.'
            : s.contains('409')
                ? 'الرمز مستخدم أو غير صالح.'
                : 'تعذّر التفعيل. تحقق من الرمز.';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('الاشتراك')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Icon(Icons.card_membership, size: 64, color: scheme.primary),
            const SizedBox(height: 16),
            Text('تفعيل فصل دراسي',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'لكل فصل اشتراك مستقل. أدخل الرمز الذي حصلت عليه من الإدارة '
              'لتفعيل محتوى الفصل.',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _code,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(
                labelText: 'رمز التفعيل',
                prefixIcon: Icon(Icons.vpn_key_outlined),
              ),
            ),
            if (_message != null) ...[
              const SizedBox(height: 12),
              Text(_message!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: _success ? Colors.green : scheme.error)),
            ],
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _busy ? null : _redeem,
              child: _busy
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('تفعيل'),
            ),
            if (_success)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('العودة'),
                ),
              ),
            const SizedBox(height: 24),
            Text('الفصول المتاحة: ${Config.semesters.map((s) => s.labelAr).join(' · ')}',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
