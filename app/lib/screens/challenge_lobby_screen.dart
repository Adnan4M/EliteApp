import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../state/auth_controller.dart';
import '../models.dart';
import '../widgets/character_widget.dart';
import '../widgets/common.dart';
import 'challenge_game_screen.dart';

/// Waiting room — shows connected players, share invite code, host starts game.
class ChallengeLobbyScreen extends StatefulWidget {
  final int challengeId;
  final bool isHost;
  final String? inviteCode;

  const ChallengeLobbyScreen({
    super.key,
    required this.challengeId,
    required this.isHost,
    this.inviteCode,
  });

  @override
  State<ChallengeLobbyScreen> createState() => _ChallengeLobbyScreenState();
}

class _ChallengeLobbyScreenState extends State<ChallengeLobbyScreen> {
  WebSocketChannel? _ws;
  List<Map<String, dynamic>> _players = [];
  bool _connecting = true;
  StreamSubscription? _sub;
  Timer? _pingTimer;
  String? _inviteCode;
  bool _handedOff = false;

  @override
  void initState() {
    super.initState();
    _inviteCode = _inviteCode;
    _connect();
    if (widget.isHost && _inviteCode == null) _fetchCode();
  }

  Future<void> _fetchCode() async {
    try {
      final api = context.read<AuthController>().api;
      final data = await api.getChallenge(widget.challengeId);
      if (mounted) setState(() => _inviteCode = data['invite_code'] as String?);
    } catch (_) {}
  }

  @override
  void dispose() {
    _pingTimer?.cancel();
    if (!_handedOff) {
      _sub?.cancel();
      _ws?.sink.close();
    }
    super.dispose();
  }

  void _connect() {
    final auth = context.read<AuthController>();
    final token = auth.token ?? '';
    final url = auth.api.challengeWsUrl(widget.challengeId, token);
    _ws = WebSocketChannel.connect(Uri.parse(url));
    _sub = _ws!.stream.listen(
      _onMessage,
      onError: (_) => setState(() => _connecting = false),
      onDone: () => setState(() => _connecting = false),
    );
    // Send hello shortly after connecting so the server replies with current state.
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _ws?.sink.add(jsonEncode({'type': 'hello'}));
    });
    // Periodic ping so the player list stays live.
    _pingTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (mounted) _ws?.sink.add(jsonEncode({'type': 'ping'}));
    });
  }

  void _onMessage(dynamic raw) {
    final msg = jsonDecode(raw as String) as Map<String, dynamic>;
    final type = msg['type'] as String?;
    if (type == 'lobby') {
      setState(() {
        _connecting = false;
        _players = (msg['players'] as List)
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } else if (type == 'start') {
      _handedOff = true;
      _pingTimer?.cancel();
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ChallengeGameScreen(
          challengeId: widget.challengeId,
          ws: _ws!,
          sub: _sub!,
          totalQuestions: msg['total_questions'] as int? ?? 10,
        ),
      ));
    } else if (type == 'error') {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(msg['message'] as String? ?? 'حدث خطأ'),
            backgroundColor: Theme.of(context).colorScheme.error,
            duration: const Duration(seconds: 5),
          ),
        );
      }
    } else if (type == 'cancelled' || type == 'expired') {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(type == 'expired' ? 'انتهت مدة الغرفة' : 'تم إلغاء الغرفة')),
        );
        Navigator.of(context).pop();
      }
    }
  }

  Future<void> _confirmCancel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('إنهاء الغرفة؟'),
        content: const Text('سيتم إلغاء الغرفة وطرد جميع اللاعبين.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(_).pop(false),
              child: const Text('تراجع')),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error),
              onPressed: () => Navigator.of(_).pop(true),
              child: const Text('إنهاء')),
        ],
      ),
    );
    if (confirmed == true) _cancelChallenge();
  }

  Future<void> _cancelChallenge() async {
    try {
      final api = context.read<AuthController>().api;
      await api.client.delete('/challenges/${widget.challengeId}');
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('خطأ: $e')));
      }
    }
  }

  void _startGame() {
    _ws?.sink.add(jsonEncode({'type': 'start'}));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('غرفة الانتظار'),
        actions: [
          if (widget.isHost)
            IconButton(
              icon: const Icon(Icons.close),
              tooltip: 'إلغاء الغرفة',
              onPressed: _cancelChallenge,
            ),
        ],
      ),
      body: _connecting
          ? const Loading()
          : Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_inviteCode != null) ...[
                    GestureDetector(
                      onTap: () {
                        Clipboard.setData(ClipboardData(text: _inviteCode!));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('تم نسخ الكود')),
                        );
                      },
                      child: Card(
                        color: scheme.primaryContainer,
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(children: [
                            Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                              Text('كود الدعوة',
                                  style: TextStyle(color: scheme.onPrimaryContainer)),
                              const SizedBox(width: 6),
                              Icon(Icons.copy, size: 16, color: scheme.onPrimaryContainer),
                            ]),
                            const SizedBox(height: 4),
                            Text(
                              _inviteCode!,
                              style: TextStyle(
                                  fontSize: 32,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 8,
                                  color: scheme.onPrimaryContainer),
                            ),
                            const SizedBox(height: 4),
                            Text('اضغط لنسخ الكود',
                                style: TextStyle(
                                    fontSize: 11, color: scheme.onPrimaryContainer.withOpacity(0.7))),
                          ]),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  Text(
                    'اللاعبون (${_players.length})',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Expanded(
                    child: ListView.builder(
                      itemCount: _players.length,
                      itemBuilder: (_, i) {
                        final p = _players[i];
                        final skinData = p['skin'] as Map<String, dynamic>?;
                        final skin = skinData != null ? SkinInfo.fromJson(skinData) : null;
                        return ListTile(
                          leading: CharacterWidget(
                            skin: skin,
                            gender: p['gender'] as String?,
                            size: 40,
                          ),
                          title: Text(p['name'] as String),
                        );
                      },
                    ),
                  ),
                  if (widget.isHost) ...[
                    FilledButton.icon(
                      onPressed: _players.isNotEmpty ? _startGame : null,
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('ابدأ اللعبة'),
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      onPressed: _confirmCancel,
                      icon: Icon(Icons.stop_circle_outlined,
                          color: Theme.of(context).colorScheme.error),
                      label: Text('إنهاء الغرفة',
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error)),
                      style: OutlinedButton.styleFrom(
                        side: BorderSide(
                            color: Theme.of(context).colorScheme.error),
                      ),
                    ),
                  ],
                  if (!widget.isHost)
                    const Center(
                        child: Text('في انتظار أن يبدأ المضيف اللعبة...')),
                ],
              ),
            ),
    );
  }
}
