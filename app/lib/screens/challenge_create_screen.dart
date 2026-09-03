import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';
import 'challenge_lobby_screen.dart';

/// Pick subject, chapters, type (open or pair) then create a challenge room.
class ChallengeCreateScreen extends StatefulWidget {
  final String? subjectId;
  final String? subjectName;
  final List<String> preselectedChapters;
  final String type;
  final int? partnerId;

  const ChallengeCreateScreen({
    super.key,
    this.subjectId,
    this.subjectName,
    this.preselectedChapters = const [],
    this.type = 'open',
    this.partnerId,
  });

  @override
  State<ChallengeCreateScreen> createState() => _ChallengeCreateScreenState();
}

class _ChallengeCreateScreenState extends State<ChallengeCreateScreen> {
  bool _loading = false;
  bool _curriculumLoading = true;
  bool _isPrivate = false;
  int _questionCount = 10;

  List<SubjectCurriculum> _curriculum = [];
  String? _selectedSubjectId;
  final Set<String> _selectedChapters = {};

  @override
  void initState() {
    super.initState();
    _selectedSubjectId = widget.subjectId;
    _selectedChapters.addAll(widget.preselectedChapters);
    _loadCurriculum();
  }

  Future<void> _loadCurriculum() async {
    setState(() => _curriculumLoading = true);
    try {
      final auth = context.read<AuthController>();
      final list = await auth.api.curriculum(semester: auth.semester);
      if (!mounted) return;
      // Deduplicate by subjectId — keep first occurrence
      final seen = <String>{};
      final deduped = list.where((s) => seen.add(s.subjectId)).toList();
      setState(() {
        _curriculum = deduped;
        _curriculumLoading = false;
        // Auto-select chapters when subject is pre-set but chapters list is empty
        if (_selectedSubjectId != null && _selectedChapters.isEmpty) {
          final subj = _curriculum.firstWhere(
            (s) => s.subjectId == _selectedSubjectId,
            orElse: () => SubjectCurriculum(subjectId: '', nameAr: '', chapters: []),
          );
          if (subj.subjectId.isNotEmpty) {
            _selectedChapters.addAll(subj.chapters.map((c) => c.key));
          }
        }
      });
    } catch (e) {
      if (mounted) setState(() => _curriculumLoading = false);
    }
  }

  SubjectCurriculum? get _currentSubject {
    if (_selectedSubjectId == null) return null;
    try {
      return _curriculum.firstWhere((s) => s.subjectId == _selectedSubjectId);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('تحدٍّ جديد')),
      body: SafeArea(
        top: false,
        child: Column(
        children: [
          // ── Privacy toggle (open challenges only) ──
          if (widget.type == 'open')
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(children: [
                Icon(_isPrivate ? Icons.lock : Icons.lock_open, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('غرفة خاصة',
                          style: TextStyle(fontWeight: FontWeight.bold)),
                      Text(
                        _isPrivate
                            ? 'الدخول فقط بكود الدعوة'
                            : 'الغرفة مفتوحة للجميع',
                        style: const TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
                Switch(
                  value: _isPrivate,
                  onChanged: (v) => setState(() => _isPrivate = v),
                ),
              ]),
            ),

          // ── Question count slider ──
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Row(children: [
              const Icon(Icons.quiz_outlined, size: 20),
              const SizedBox(width: 10),
              Text('عدد الأسئلة: $_questionCount',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
              Expanded(
                child: Slider(
                  value: _questionCount.toDouble(),
                  min: 5,
                  max: 30,
                  divisions: 5,
                  label: '$_questionCount',
                  onChanged: (v) => setState(() => _questionCount = v.round()),
                ),
              ),
            ]),
          ),

          if (_curriculumLoading)
            const Expanded(child: Loading())
          else ...[
            // ── Subject picker (always shown) ──
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: DropdownButtonFormField<String>(
                decoration: const InputDecoration(
                  labelText: 'اختر المادة',
                  border: OutlineInputBorder(),
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                ),
                value: _selectedSubjectId,
                items: _curriculum.map((s) => DropdownMenuItem(
                  value: s.subjectId,
                  child: Text(s.nameAr),
                )).toList(),
                onChanged: (v) {
                  if (v == null) return;
                  final subj = _curriculum.firstWhere((s) => s.subjectId == v);
                  setState(() {
                    _selectedSubjectId = v;
                    _selectedChapters
                      ..clear()
                      ..addAll(subj.chapters.map((c) => c.key));
                  });
                },
              ),
            ),

            // ── Chapter selection ──
            if (_currentSubject != null) ...[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      'اختر الفصول (${_selectedChapters.length} مختار)',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                  TextButton(
                    onPressed: () => setState(() {
                      _selectedChapters.addAll(_currentSubject!.chapters.map((c) => c.key));
                    }),
                    child: const Text('الكل'),
                  ),
                  TextButton(
                    onPressed: () => setState(() => _selectedChapters.clear()),
                    child: const Text('لا شيء'),
                  ),
                ]),
              ),
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  itemCount: _currentSubject!.chapters.length,
                  itemBuilder: (_, i) {
                    final ch = _currentSubject!.chapters[i];
                    final isSelected = _selectedChapters.contains(ch.key);

                    return Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Card(
                        margin: EdgeInsets.zero,
                        color: isSelected ? scheme.primaryContainer : null,
                        child: InkWell(
                          borderRadius: BorderRadius.circular(12),
                          onTap: () => setState(() {
                            if (isSelected) {
                              _selectedChapters.remove(ch.key);
                            } else {
                              _selectedChapters.add(ch.key);
                            }
                          }),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                            child: Row(children: [
                              Icon(
                                isSelected ? Icons.check_box : Icons.check_box_outline_blank,
                                color: isSelected ? scheme.primary : scheme.onSurfaceVariant,
                                size: 20,
                              ),
                              const SizedBox(width: 10),
                              if (ch.number != null) ...[
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: isSelected ? scheme.primary : scheme.primaryContainer,
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: Text(
                                    '${ch.number}',
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                      color: isSelected ? scheme.onPrimary : scheme.onPrimaryContainer,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                              ],
                              Expanded(
                                child: Text(
                                  ch.name,
                                  style: TextStyle(
                                    color: isSelected ? scheme.onPrimaryContainer : null,
                                  ),
                                ),
                              ),
                            ]),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ] else
              const Expanded(
                child: Center(
                  child: Text('اختر مادة أولاً', style: TextStyle(color: Colors.grey)),
                ),
              ),

            // ── Create button ──
            Padding(
              padding: const EdgeInsets.all(16),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                onPressed: (_loading || _selectedSubjectId == null || _selectedChapters.isEmpty)
                    ? null
                    : _create,
                icon: _loading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.play_arrow),
                label: Text(_selectedChapters.isEmpty
                    ? 'اختر فصلاً على الأقل'
                    : 'إنشاء الغرفة (${_selectedChapters.length} فصل)'),
              ),
              ),
            ),
          ],
        ],
      ),
      ),
    );
  }

  Future<void> _create() async {
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthController>();
      final result = await auth.api.createChallenge(
        type: widget.type,
        semester: auth.semester,
        subjectId: _selectedSubjectId!,
        chapters: _selectedChapters.toList(),
        partnerId: widget.partnerId,
        isPrivate: _isPrivate,
        questionCount: _questionCount,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ChallengeLobbyScreen(
          challengeId: result['challenge_id'] as int,
          isHost: true,
          inviteCode: result['invite_code'] as String?,
        ),
      ));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('خطأ: $e')));
        setState(() => _loading = false);
      }
    }
  }
}
