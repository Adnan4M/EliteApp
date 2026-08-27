import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/auth_controller.dart';

/// 6-digit email verification screen shown after registration.
class VerifyScreen extends StatefulWidget {
  final String email;
  final String password;
  const VerifyScreen({super.key, required this.email, required this.password});

  @override
  State<VerifyScreen> createState() => _VerifyScreenState();
}

class _VerifyScreenState extends State<VerifyScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  bool _resending = false;
  String? _error;
  String? _success;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final code = _code.text.trim();
    if (code.length != 6) {
      setState(() => _error = 'أدخل الرمز المكوّن من 6 أرقام');
      return;
    }
    setState(() { _busy = true; _error = null; });
    try {
      final auth = context.read<AuthController>();
      await auth.api.verifyEmail(widget.email, code);
      // Now log in
      await auth.login(widget.email, widget.password);
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      setState(() => _error = _friendly(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    setState(() { _resending = true; _error = null; _success = null; });
    try {
      final auth = context.read<AuthController>();
      await auth.api.resendCode(widget.email, widget.password);
      setState(() => _success = 'تم إرسال رمز جديد');
    } catch (e) {
      setState(() => _error = _friendly(e));
    } finally {
      if (mounted) setState(() => _resending = false);
    }
  }

  String _friendly(Object e) {
    final s = e.toString();
    if (s.contains('غير صحيح')) return 'الرمز غير صحيح';
    if (s.contains('صلاحية')) return 'انتهت صلاحية الرمز. اطلب رمزاً جديداً.';
    if (s.contains('502')) return 'فشل إرسال الرمز. حاول مرة أخرى.';
    return 'خطأ: $s';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('تحقق من بريدك')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(Icons.mark_email_read_outlined, size: 64, color: scheme.primary),
              const SizedBox(height: 16),
              Text('أرسلنا رمز تحقق إلى',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(widget.email,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontWeight: FontWeight.bold, color: scheme.primary)),
              const SizedBox(height: 24),
              TextField(
                controller: _code,
                keyboardType: TextInputType.number,
                maxLength: 6,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 28, letterSpacing: 12, fontWeight: FontWeight.bold),
                decoration: const InputDecoration(
                  hintText: '------',
                  counterText: '',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: scheme.error)),
              ],
              if (_success != null) ...[
                const SizedBox(height: 12),
                Text(_success!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: scheme.primary)),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy ? null : _verify,
                child: _busy
                    ? const SizedBox(
                        height: 22,
                        width: 22,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('تأكيد'),
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: _resending ? null : _resend,
                child: _resending
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('إعادة إرسال الرمز'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
