import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/auth_controller.dart';
import 'verify_screen.dart';

/// Combined sign-in / register screen (email + password).
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _phone = TextEditingController();

  bool _isRegister = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = context.read<AuthController>();
    try {
      if (_isRegister) {
        await auth.register(
          _email.text.trim(),
          _password.text,
          name: _name.text.trim(),
          phone: _phone.text.trim(),
        );
        // After registration, go to verification screen
        if (mounted) {
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => VerifyScreen(
              email: _email.text.trim(),
              password: _password.text,
            ),
          ));
        }
      } else {
        await auth.login(_email.text.trim(), _password.text);
      }
    } catch (e) {
      final msg = _friendly(e);
      if (msg == '_NEEDS_VERIFY') {
        if (mounted) {
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => VerifyScreen(
              email: _email.text.trim(),
              password: _password.text,
            ),
          ));
        }
      } else {
        setState(() => _error = msg);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _friendly(Object e) {
    final s = e.toString();
    if (s.contains('EMAIL_NOT_VERIFIED')) return '_NEEDS_VERIFY';
    if (s.contains('409') && s.contains('هاتف')) return 'رقم الهاتف مسجّل بالفعل.';
    if (s.contains('409')) return 'هذا البريد مسجّل بالفعل.';
    if (s.contains('401')) return 'البريد أو كلمة المرور غير صحيحة.';
    if (s.contains('422') && s.contains('Gmail')) {
      return 'يُسمح فقط بالبريد من Gmail أو Outlook أو Hotmail';
    }
    if (s.contains('502')) return 'فشل إرسال رمز التحقق. حاول مرة أخرى.';
    return 'خطأ: $s';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.school_rounded, size: 72, color: scheme.primary),
                  const SizedBox(height: 12),
                  Text('X Word',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineMedium),
                  Text('مساعدك الذكي للسنة التحضيرية',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 32),
                  if (_isRegister) ...[
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: TextFormField(
                        controller: _name,
                        decoration: const InputDecoration(
                          labelText: 'الاسم (اختياري)',
                          prefixIcon: Icon(Icons.person_outline),
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: TextFormField(
                        controller: _phone,
                        keyboardType: TextInputType.phone,
                        decoration: const InputDecoration(
                          labelText: 'رقم الهاتف',
                          prefixIcon: Icon(Icons.phone_outlined),
                          hintText: '09XXXXXXXX',
                        ),
                        validator: (v) {
                          if (v == null || v.trim().isEmpty) {
                            return 'أدخل رقم الهاتف';
                          }
                          final digits = v.trim().replaceAll(RegExp(r'[^0-9+]'), '');
                          if (digits.length < 9) return 'رقم هاتف غير صحيح';
                          return null;
                        },
                      ),
                    ),
                  ],
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'البريد الإلكتروني',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    validator: (v) {
                      if (v == null || !v.contains('@')) return 'أدخل بريداً صحيحاً';
                      final domain = v.trim().split('@').last.toLowerCase();
                      if (!['gmail.com', 'outlook.com', 'hotmail.com']
                          .contains(domain)) {
                        return 'يُسمح فقط بـ Gmail أو Outlook أو Hotmail';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _password,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'كلمة المرور',
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                    validator: (v) => (v == null || v.length < 6)
                        ? 'كلمة المرور 6 أحرف على الأقل'
                        : null,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: scheme.error)),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : Text(_isRegister ? 'إنشاء حساب' : 'تسجيل الدخول'),
                  ),
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _isRegister = !_isRegister;
                              _error = null;
                            }),
                    child: Text(_isRegister
                        ? 'لديك حساب؟ سجّل الدخول'
                        : 'ليس لديك حساب؟ أنشئ واحداً (تجربة 7 أيام)'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
