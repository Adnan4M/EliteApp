import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../state/auth_controller.dart';
import 'search_result_screen.dart';
import 'subscription_screen.dart';

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
      if (result.total == 0) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('لم أجد «$keyword» في هذا الفصل')));
        return;
      }
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => SearchResultScreen(
            semester: widget.semester.value, result: result),
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
