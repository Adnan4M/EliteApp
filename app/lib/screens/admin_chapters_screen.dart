import 'package:flutter/material.dart';
import '../api/api_client.dart';
import '../config.dart';

/// Admin screen for managing chapter lists per subject.
class AdminChaptersScreen extends StatefulWidget {
  const AdminChaptersScreen({super.key});

  @override
  State<AdminChaptersScreen> createState() => _AdminChaptersScreenState();
}

class _AdminChaptersScreenState extends State<AdminChaptersScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  final _adminKey = TextEditingController();
  bool _authed = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    _adminKey.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_authed) return _loginScreen();
    return Scaffold(
      appBar: AppBar(
        title: const Text('إدارة الفصول'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [Tab(text: 'الفصل الأول'), Tab(text: 'الفصل الثاني')],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _SemesterEditor(semester: 'first', adminKey: _adminKey.text),
          _SemesterEditor(semester: 'second', adminKey: _adminKey.text),
        ],
      ),
    );
  }

  Widget _loginScreen() => Scaffold(
        appBar: AppBar(title: const Text('لوحة الإدارة')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextField(
                controller: _adminKey,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'مفتاح الإدارة',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () => setState(() => _authed = true),
                child: const Text('دخول'),
              ),
            ],
          ),
        ),
      );
}

// ── semester editor ──────────────────────────────────────────────────────────

class _SemesterEditor extends StatefulWidget {
  final String semester;
  final String adminKey;
  const _SemesterEditor({required this.semester, required this.adminKey});

  @override
  State<_SemesterEditor> createState() => _SemesterEditorState();
}

class _SemesterEditorState extends State<_SemesterEditor>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  List<_SubjectData>? _subjects;
  String? _error;

  static const _knownSubjects = {
    'first': ['physics', 'chemistry', 'biology', 'history'],
    'second': ['anatomy', 'genetics', 'physiology', 'statistics'],
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  ApiClient get _client => ApiClient(
        baseUrl: Config.apiBase,
        extraHeaders: {'X-Admin-Key': widget.adminKey},
      );

  Future<void> _load() async {
    try {
      final raw = await _client.get('/admin/chapters/${widget.semester}') as List;
      final loaded = <_SubjectData>{};
      for (final s in raw) {
        final id = s['subject_id'] as String;
        final chs = (s['chapters'] as List)
            .map((c) => _Chapter(
                  key: c['key'] as String,
                  name: c['name'] as String,
                ))
            .toList();
        loaded.add(_SubjectData(id, chs));
      }
      // Ensure all known subjects appear even if empty
      final knownIds = _knownSubjects[widget.semester] ?? [];
      for (final id in knownIds) {
        if (!loaded.any((s) => s.id == id)) {
          loaded.add(_SubjectData(id, []));
        }
      }
      if (mounted) setState(() => _subjects = loaded.toList());
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _save(_SubjectData subject) async {
    try {
      final body = subject.chapters
          .map((c) => {'key': c.key, 'name': c.name})
          .toList();
      await _client.put(
          '/admin/chapters/${widget.semester}/${subject.id}', body: body);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تم الحفظ')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('خطأ: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_error != null) {
      return Center(child: Text('خطأ: $_error'));
    }
    if (_subjects == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: _subjects!.length,
      itemBuilder: (_, i) => _SubjectCard(
        subject: _subjects![i],
        onSave: () => _save(_subjects![i]),
      ),
    );
  }
}

// ── subject card ─────────────────────────────────────────────────────────────

class _SubjectCard extends StatefulWidget {
  final _SubjectData subject;
  final VoidCallback onSave;
  const _SubjectCard({required this.subject, required this.onSave});

  @override
  State<_SubjectCard> createState() => _SubjectCardState();
}

class _SubjectCardState extends State<_SubjectCard> {
  bool _expanded = false;

  void _addChapter() {
    final nameCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('إضافة فصل'),
        content: TextField(
          controller: nameCtrl,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'اسم الفصل'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('إلغاء')),
          ElevatedButton(
            onPressed: () {
              final name = nameCtrl.text.trim();
              if (name.isNotEmpty) {
                final key = name.replaceAll(' ', '_').substring(
                    0, name.length > 32 ? 32 : name.length);
                setState(() => widget.subject.chapters
                    .add(_Chapter(key: key, name: name)));
              }
              Navigator.pop(context);
            },
            child: const Text('إضافة'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.subject;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        initiallyExpanded: _expanded,
        onExpansionChanged: (v) => setState(() => _expanded = v),
        title: Text(s.id,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text('${s.chapters.length} فصل'),
        children: [
          ReorderableListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: s.chapters.length,
            onReorder: (oldIndex, newIndex) {
              setState(() {
                if (newIndex > oldIndex) newIndex--;
                final ch = s.chapters.removeAt(oldIndex);
                s.chapters.insert(newIndex, ch);
              });
            },
            itemBuilder: (_, i) {
              final ch = s.chapters[i];
              return ListTile(
                key: ValueKey(ch.key + i.toString()),
                leading: ReorderableDragStartListener(
                    index: i,
                    child: const Icon(Icons.drag_handle)),
                title: Text(ch.name),
                subtitle: Text(ch.key,
                    style: const TextStyle(fontSize: 11)),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.red),
                  onPressed: () =>
                      setState(() => s.chapters.removeAt(i)),
                ),
              );
            },
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                TextButton.icon(
                  onPressed: _addChapter,
                  icon: const Icon(Icons.add),
                  label: const Text('إضافة فصل'),
                ),
                const Spacer(),
                ElevatedButton.icon(
                  onPressed: widget.onSave,
                  icon: const Icon(Icons.save),
                  label: const Text('حفظ'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── data classes ─────────────────────────────────────────────────────────────

class _Chapter {
  String key;
  String name;
  _Chapter({required this.key, required this.name});
}

class _SubjectData {
  final String id;
  final List<_Chapter> chapters;
  _SubjectData(this.id, this.chapters);
}
