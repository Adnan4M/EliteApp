import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/character_widget.dart';
import 'challenge_result_screen.dart';

class ChallengeGameScreen extends StatefulWidget {
  final int challengeId;
  final WebSocketChannel ws;
  final StreamSubscription sub;
  final int totalQuestions;

  const ChallengeGameScreen({
    super.key,
    required this.challengeId,
    required this.ws,
    required this.sub,
    required this.totalQuestions,
  });

  @override
  State<ChallengeGameScreen> createState() => _ChallengeGameScreenState();
}

class _ChallengeGameScreenState extends State<ChallengeGameScreen> {
  WebSocketChannel? _ws;
  StreamSubscription? _sub;

  Map<String, dynamic>? _question;
  int _secondsLeft = 30;
  Timer? _timer;
  int? _myAnswer;
  int? _correctIndex;
  Map<String, int> _roundScores = {};
  List<Map<String, dynamic>> _leaderboard = [];
  bool _revealing = false;
  DateTime _questionStart = DateTime.now();
  int? _myUserId;

  static const _optionColors = [
    Color(0xFFE63946),
    Color(0xFF457B9D),
    Color(0xFF2A9D8F),
    Color(0xFFE9C46A),
  ];
  static const _optionLabels = ['أ', 'ب', 'ج', 'د'];

  @override
  void initState() {
    super.initState();
    _myUserId = context.read<AuthController>().userId;
    widget.sub.onData((_) {});
    widget.sub.onError((_) {});
    widget.sub.onDone(() {});
    _connect();
  }

  void _connect() {
    final auth = context.read<AuthController>();
    final token = auth.token ?? '';
    final url = auth.api.challengeWsUrl(widget.challengeId, token);
    _ws = WebSocketChannel.connect(Uri.parse(url));
    _sub = _ws!.stream.listen(_onMessage, onError: (_) {}, onDone: () {});
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) _ws?.sink.add(jsonEncode({'type': 'hello'}));
    });
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted && _question == null) {
        _ws?.sink.add(jsonEncode({'type': 'hello'}));
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _sub?.cancel();
    _ws?.sink.close();
    super.dispose();
  }

  void _onMessage(dynamic raw) {
    final msg = jsonDecode(raw as String) as Map<String, dynamic>;
    final type = msg['type'] as String?;

    if (type == 'question') {
      setState(() {
        _question = msg;
        _secondsLeft = msg['seconds'] as int? ?? 30;
        _myAnswer = null;
        _correctIndex = null;
        _roundScores = {};
        _leaderboard = [];
        _revealing = false;
        _questionStart = DateTime.now();
      });
      _startTimer();
    } else if (type == 'reveal') {
      _timer?.cancel();
      setState(() {
        _revealing = true;
        _correctIndex = msg['correct_index'] as int?;
        _roundScores = (msg['round_scores'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v as int));
        _leaderboard = (msg['leaderboard'] as List? ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } else if (type == 'finished') {
      final leaderboard = (msg['leaderboard'] as List)
          .map((e) => e as Map<String, dynamic>)
          .toList();
      final xpAwards = (msg['xp_awards'] as Map<String, dynamic>)
          .map((k, v) => MapEntry(k, v as int));
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ChallengeResultScreen(
          leaderboard: leaderboard,
          xpAwards: xpAwards,
        ),
      ));
    }
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_secondsLeft <= 0) {
        t.cancel();
        // Auto-submit if no answer was given — sends index -1 as timeout
        if (_myAnswer == null && !_revealing) {
          final elapsed = DateTime.now().difference(_questionStart).inMilliseconds / 1000;
          setState(() => _myAnswer = -1);
          _ws?.sink.add(jsonEncode({'type': 'answer', 'index': -1, 'elapsed': elapsed}));
        }
        return;
      }
      setState(() => _secondsLeft--);
    });
  }

  void _answer(int idx) {
    if (_myAnswer != null || _revealing) return;
    final elapsed = DateTime.now().difference(_questionStart).inMilliseconds / 1000;
    setState(() => _myAnswer = idx);
    _ws?.sink.add(jsonEncode({'type': 'answer', 'index': idx, 'elapsed': elapsed}));
  }

  @override
  Widget build(BuildContext context) {
    if (_question == null) {
      return Scaffold(
        body: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text('جارٍ تحميل الأسئلة...', style: Theme.of(context).textTheme.titleMedium),
        ])),
      );
    }

    final scheme = Theme.of(context).colorScheme;
    final q = _question!;
    final qIndex = q['index'] as int;
    final total = q['total'] as int;
    final questionText = q['question'] as String;
    final options = (q['options'] as List).map((e) => e.toString()).toList();

    return Scaffold(
      backgroundColor: scheme.surface,
      body: SafeArea(
        child: Column(children: [
          // ── Header ──
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(children: [
              Text('سؤال ${qIndex + 1} / $total',
                  style: Theme.of(context).textTheme.titleSmall),
              const Spacer(),
              _TimerCircle(seconds: _secondsLeft, total: 30),
            ]),
          ),
          LinearProgressIndicator(value: (qIndex + 1) / total, minHeight: 3),

          // ── Question ──
          Container(
            constraints: const BoxConstraints(minHeight: 80, maxHeight: 140),
            margin: const EdgeInsets.fromLTRB(12, 8, 12, 6),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: scheme.primaryContainer,
              borderRadius: BorderRadius.circular(14),
            ),
            alignment: Alignment.center,
            child: Text(questionText,
                textAlign: TextAlign.center,
                maxLines: 5,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: scheme.onPrimaryContainer)),
          ),

          // ── Options ──
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: _revealing
                  ? _RevealPanel(
                      myAnswer: _myAnswer,
                      correctIndex: _correctIndex,
                      roundScores: _roundScores,
                      leaderboard: _leaderboard,
                      myUserId: _myUserId,
                      options: options,
                      optionColors: _optionColors,
                      optionLabels: _optionLabels,
                      cardColor: _cardColor,
                      onAnswer: _answer,
                    )
                  : Column(children: [
                      Expanded(
                        child: Row(children: [
                          _OptionCard(
                            label: _optionLabels[0],
                            text: options[0],
                            color: _cardColor(0, _optionColors[0]),
                            selected: _myAnswer == 0,
                            correct: false,
                            onTap: () => _answer(0),
                          ),
                          const SizedBox(width: 8),
                          _OptionCard(
                            label: _optionLabels[1],
                            text: options[1],
                            color: _cardColor(1, _optionColors[1]),
                            selected: _myAnswer == 1,
                            correct: false,
                            onTap: () => _answer(1),
                          ),
                        ]),
                      ),
                      const SizedBox(height: 8),
                      Expanded(
                        child: Row(children: [
                          _OptionCard(
                            label: _optionLabels[2],
                            text: options[2],
                            color: _cardColor(2, _optionColors[2]),
                            selected: _myAnswer == 2,
                            correct: false,
                            onTap: () => _answer(2),
                          ),
                          const SizedBox(width: 8),
                          _OptionCard(
                            label: _optionLabels[3],
                            text: options.length > 3 ? options[3] : '',
                            color: _cardColor(3, _optionColors[3]),
                            selected: _myAnswer == 3,
                            correct: false,
                            onTap: () => _answer(3),
                          ),
                        ]),
                      ),
                    ]),
            ),
          ),
        ]),
      ),
    );
  }

  Color _cardColor(int idx, Color base) {
    if (!_revealing) return _myAnswer == idx ? base.withValues(alpha: 0.75) : base;
    if (_correctIndex == idx) return Colors.green;
    if (_myAnswer == idx) return Colors.red.shade700;
    return base.withValues(alpha: 0.35);
  }
}

// ── Option card ──────────────────────────────────────────────────────────────

class _OptionCard extends StatelessWidget {
  final String label;
  final String text;
  final Color color;
  final bool selected;
  final bool correct;
  final VoidCallback onTap;

  const _OptionCard({
    required this.label,
    required this.text,
    required this.color,
    required this.selected,
    required this.correct,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(12),
            border: selected ? Border.all(color: Colors.white, width: 3) : null,
          ),
          child: Stack(children: [
            Center(child: Text('$label. $text',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: text.length > 80 ? 10 : text.length > 40 ? 12 : 14)),
            ),
            if (correct)
              const Positioned(top: 0, left: 0,
                  child: Icon(Icons.check_circle, color: Colors.white, size: 16)),
          ]),
        ),
      ),
    );
  }
}

// ── Reveal leaderboard ───────────────────────────────────────────────────────

class _RevealPanel extends StatelessWidget {
  final int? myAnswer;
  final int? correctIndex;
  final Map<String, int> roundScores;
  final List<Map<String, dynamic>> leaderboard;
  final int? myUserId;
  final List<String> options;
  final List<Color> optionColors;
  final List<String> optionLabels;
  final Color Function(int, Color) cardColor;
  final void Function(int) onAnswer;

  const _RevealPanel({
    required this.myAnswer,
    required this.correctIndex,
    required this.roundScores,
    required this.leaderboard,
    required this.options,
    required this.optionColors,
    required this.optionLabels,
    required this.cardColor,
    required this.onAnswer,
    this.myUserId,
  });

  @override
  Widget build(BuildContext context) {
    final correct = myAnswer == correctIndex;
    final scheme = Theme.of(context).colorScheme;
    final myScore = myUserId != null ? (roundScores[myUserId.toString()] ?? 0) : 0;

    return Column(children: [
      // Options grid (revealed state)
      SizedBox(
        height: 80,
        child: Column(children: [
          Expanded(child: Row(children: [
            _OptionCard(label: optionLabels[0], text: options[0], color: cardColor(0, optionColors[0]), selected: myAnswer == 0, correct: correctIndex == 0, onTap: () {}),
            const SizedBox(width: 8),
            _OptionCard(label: optionLabels[1], text: options[1], color: cardColor(1, optionColors[1]), selected: myAnswer == 1, correct: correctIndex == 1, onTap: () {}),
          ])),
          const SizedBox(height: 4),
          Expanded(child: Row(children: [
            _OptionCard(label: optionLabels[2], text: options[2], color: cardColor(2, optionColors[2]), selected: myAnswer == 2, correct: correctIndex == 2, onTap: () {}),
            const SizedBox(width: 8),
            _OptionCard(label: optionLabels[3], text: options.length > 3 ? options[3] : '', color: cardColor(3, optionColors[3]), selected: myAnswer == 3, correct: correctIndex == 3, onTap: () {}),
          ])),
        ]),
      ),
      const SizedBox(height: 8),
      // Result + leaderboard
      Expanded(
        child: Container(
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 8),
              decoration: BoxDecoration(
                color: correct ? Colors.green : Colors.red.shade600,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(14)),
              ),
              child: Text(
                correct ? '+$myScore نقطة! إجابة صحيحة ✓' : 'إجابة خاطئة ✗',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
              ),
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.all(6),
                itemCount: leaderboard.length,
                itemBuilder: (_, i) {
                  final p = leaderboard[i];
                  final medal = i == 0 ? '🥇' : i == 1 ? '🥈' : i == 2 ? '🥉' : '${i + 1}.';
                  final skinData = p['skin'] as Map<String, dynamic>?;
                  final skin = skinData != null ? SkinInfo.fromJson(skinData) : null;
                  final gender = p['gender'] as String?;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(children: [
                      SizedBox(width: 24, child: Text(medal, style: const TextStyle(fontSize: 14))),
                      CharacterWidget(skin: skin, gender: gender, size: 28),
                      const SizedBox(width: 6),
                      Expanded(child: Text(p['name'] as String,
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13))),
                      Text('${p['score']}',
                          style: TextStyle(color: scheme.primary, fontWeight: FontWeight.bold, fontSize: 13)),
                    ]),
                  );
                },
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text('السؤال التالي خلال لحظات...',
                  style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 11)),
            ),
          ]),
        ),
      ),
    ]);
  }
}

// ── Timer ────────────────────────────────────────────────────────────────────

class _TimerCircle extends StatelessWidget {
  final int seconds;
  final int total;
  const _TimerCircle({required this.seconds, required this.total});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final frac = seconds / total;
    return SizedBox(
      width: 44, height: 44,
      child: Stack(alignment: Alignment.center, children: [
        CircularProgressIndicator(
          value: frac,
          backgroundColor: scheme.surfaceContainerHighest,
          color: frac < 0.2 ? Colors.red : scheme.primary,
          strokeWidth: 4,
        ),
        Text('$seconds',
            style: TextStyle(
                fontWeight: FontWeight.bold, fontSize: 13,
                color: frac < 0.2 ? Colors.red : scheme.onSurface)),
      ]),
    );
  }
}
