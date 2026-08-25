import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../state/auth_controller.dart';
import 'search_result_screen.dart';
import 'subscription_screen.dart';

import '../widgets/common.dart';

/// Smart search entry: a field with live suggestions that opens results.
class SearchTab extends StatefulWidget {
  final ValueNotifier<String> semester;
  const SearchTab({super.key, required this.semester});

  @override
  State<SearchTab> createState() => _SearchTabState();
}

class _SearchTabState extends State<SearchTab> {
  final _controller = TextEditingController();
  Timer? _debounce;
  List<String> _suggestions = [];
  bool _busy = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    if (value.trim().length < 2) {
      setState(() => _suggestions = []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () => _fetchSuggest(value.trim()));
  }

  Future<void> _fetchSuggest(String q) async {
    final auth = context.read<AuthController>();
    try {
      final s = await auth.api.suggest(widget.semester.value, q);
      if (mounted) setState(() => _suggestions = s);
    } on ApiException catch (e) {
      if (e.isPaymentRequired && mounted) _promptSubscribe();
    } catch (_) {/* suggestions are best-effort */}
  }

  Future<void> _runSearch(String keyword) async {
    keyword = keyword.trim();
    if (keyword.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    final auth = context.read<AuthController>();
    try {
      final result = await auth.api.search(widget.semester.value, keyword);
      if (!mounted) return;
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => result.total == 0
            ? _NotFoundPage(semester: widget.semester.value, keyword: keyword)
            : SearchResultScreen(semester: widget.semester.value, result: result),
      ));
    } on ApiException catch (e) {
      if (e.isPaymentRequired) {
        _promptSubscribe();
      } else {
        _snack(e.message);
      }
    } catch (e) {
      _snack('تعذّر البحث. حاول مجدداً.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _snack(String m) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(m)));

  void _promptSubscribe() {
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const SubscriptionScreen()));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _controller,
            textInputAction: TextInputAction.search,
            onChanged: _onChanged,
            onSubmitted: _runSearch,
            decoration: InputDecoration(
              hintText: 'اكتب كلمة أو مفهوماً...',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _busy
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2)))
                  : IconButton(
                      icon: const Icon(Icons.arrow_forward),
                      onPressed: () => _runSearch(_controller.text)),
            ),
          ),
        ),
        Expanded(
          child: _suggestions.isEmpty
              ? _emptyHint(context)
              : ListView.separated(
                  itemCount: _suggestions.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final s = _suggestions[i];
                    return ListTile(
                      leading: const Icon(Icons.north_west, size: 18),
                      title: Text(s),
                      onTap: () {
                        _controller.text = s;
                        _runSearch(s);
                      },
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _emptyHint(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.menu_book_rounded,
                  size: 56,
                  color: Theme.of(context).colorScheme.onSurfaceVariant),
              const SizedBox(height: 12),
              Text(
                'ابحث في منهج فصلك.\nستحصل على كل صفحة ورد فيها المفهوم، مع تظليل الكلمة.',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      );
}

// ─── Shown when the keyword has no results in any book ───────────────────────

class _NotFoundPage extends StatefulWidget {
  final String semester;
  final String keyword;
  const _NotFoundPage({required this.semester, required this.keyword});

  @override
  State<_NotFoundPage> createState() => _NotFoundPageState();
}

class _NotFoundPageState extends State<_NotFoundPage> {
  bool _aiLoading = false;
  String? _aiResult;
  String? _aiError;

  Future<void> _searchByAI() async {
    setState(() {
      _aiLoading = true;
      _aiError = null;
    });
    try {
      final e = await context
          .read<AuthController>()
          .api
          .explanation(widget.semester, widget.keyword);
      if (mounted) setState(() => _aiResult = e.simple);
    } catch (e) {
      if (mounted) {
        String err;
        if (e is ApiException && e.isNotScientific) {
          err = 'not_scientific';
        } else if (e is ApiException) {
          err = e.message;
        } else {
          err = 'حدث خطأ. حاول مجدداً.';
        }
        setState(() => _aiError = err);
      }
    } finally {
      if (mounted) setState(() => _aiLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text('«${widget.keyword}»')),
      body: _aiResult != null
          ? _buildAIResult(scheme)
          : _buildNotFound(scheme),
    );
  }

  Widget _buildNotFound(ColorScheme scheme) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.search_off_rounded, size: 64,
                color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text(
              'لم يُعثر على «${widget.keyword}» في أي كتاب من كتب هذا الفصل.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, color: scheme.onSurface),
            ),
            const SizedBox(height: 24),
            if (_aiLoading)
              const CircularProgressIndicator()
            else if (_aiError == 'not_scientific') ...[
              const SizedBox(height: 8),
              Icon(Icons.block_rounded, size: 40,
                  color: scheme.error.withValues(alpha: 0.7)),
              const SizedBox(height: 10),
              Text(
                'يُسمح بالبحث عن المصطلحات العلمية والطبية فقط.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: scheme.error),
              ),
            ] else ...[
              if (_aiError != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_aiError!,
                      style: const TextStyle(color: Colors.red),
                      textAlign: TextAlign.center),
                ),
              FilledButton.icon(
                onPressed: _searchByAI,
                icon: const Icon(Icons.auto_awesome),
                label: const Text('اشرح بالذكاء الاصطناعي'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildAIResult(ColorScheme scheme) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          color: scheme.secondaryContainer.withValues(alpha: 0.4),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              Icon(Icons.info_outline, size: 18, color: scheme.secondary),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'هذا المصطلح غير موجود في الكتاب — الشرح أدناه من الذكاء الاصطناعي.',
                  style: TextStyle(fontSize: 13),
                ),
              ),
            ]),
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'شرح الذكاء الاصطناعي',
          icon: Icons.auto_awesome,
          child: buildMarkdown(_aiResult!),
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}
