import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config.dart';
import '../state/auth_controller.dart';
import 'notifications_tab.dart';
import 'open_challenges_screen.dart';
import 'profile_tab.dart';
import 'search_tab.dart';
import 'study_screen.dart';
import 'support_tab.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  // Proxy notifier so existing tabs that take ValueNotifier<String> still work.
  late final ValueNotifier<String> _semesterNotifier;

  static const _titles = ['حسابي', 'البحث', 'ادرس معي', 'التحديات', 'الإشعارات', 'الدعم'];

  @override
  void initState() {
    super.initState();
    final auth = context.read<AuthController>();
    _semesterNotifier = ValueNotifier(auth.semester);
    auth.addListener(_onAuthChanged);
  }

  void _onAuthChanged() {
    final sem = context.read<AuthController>().semester;
    if (_semesterNotifier.value != sem) _semesterNotifier.value = sem;
  }

  @override
  void dispose() {
    context.read<AuthController>().removeListener(_onAuthChanged);
    _semesterNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final semester = auth.semester;

    final tabs = [
      ProfileTab(semester: _semesterNotifier),
      SearchTab(semester: _semesterNotifier),
      StudyTab(semester: _semesterNotifier),
      const OpenChallengesScreen(),
      const NotificationsTab(),
      const SupportTab(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 260),
              child: SegmentedButton<String>(
                segments: Config.semesters
                    .where((s) {
                      final activated = auth.activatedSemestersForYear;
                      return activated.isEmpty || activated.contains(s.id);
                    })
                    .map((s) => ButtonSegment(
                        value: s.id,
                        label: Text(s.labelAr, overflow: TextOverflow.ellipsis)))
                    .toList(),
                selected: {semester},
                showSelectedIcon: false,
                onSelectionChanged: (sel) => auth.setSemester(sel.first),
              ),
            ),
          ),
        ],
      ),
      body: IndexedStack(index: _index, children: tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.person_outline),
              selectedIcon: Icon(Icons.person),
              label: 'حسابي'),
          NavigationDestination(
              icon: Icon(Icons.search),
              selectedIcon: Icon(Icons.search),
              label: 'البحث'),
          NavigationDestination(
              icon: Icon(Icons.groups_outlined),
              selectedIcon: Icon(Icons.groups),
              label: 'ادرس معي'),
          NavigationDestination(
              icon: Icon(Icons.sports_esports_outlined),
              selectedIcon: Icon(Icons.sports_esports),
              label: 'التحديات'),
          NavigationDestination(
              icon: Icon(Icons.notifications_outlined),
              selectedIcon: Icon(Icons.notifications),
              label: 'الإشعارات'),
          NavigationDestination(
              icon: Icon(Icons.support_agent_outlined),
              selectedIcon: Icon(Icons.support_agent),
              label: 'الدعم'),
        ],
      ),
    );
  }
}
