import 'package:flutter/material.dart';

import '../config.dart';
import 'notifications_tab.dart';
import 'profile_tab.dart';
import 'search_tab.dart';
import 'support_tab.dart';

/// Main container: bottom nav (Profile / Search / Notifications / Support)
/// with a shared semester selector in the app bar.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  // Shared across tabs; first semester is the default (trial covers it).
  final ValueNotifier<String> _semester = ValueNotifier('first');

  static const _titles = ['حسابي', 'البحث', 'الإشعارات', 'الدعم'];

  @override
  void dispose() {
    _semester.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tabs = [
      ProfileTab(semester: _semester),
      SearchTab(semester: _semester),
      const NotificationsTab(),
      const SupportTab(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          // Semester toggle affects Profile + Search.
          if (_index == 0 || _index == 1)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: ValueListenableBuilder<String>(
                valueListenable: _semester,
                builder: (context, value, _) => SegmentedButton<String>(
                  segments: Config.semesters
                      .map((s) => ButtonSegment(
                          value: s.id, label: Text(s.labelAr)))
                      .toList(),
                  selected: {value},
                  showSelectedIcon: false,
                  onSelectionChanged: (sel) => _semester.value = sel.first,
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
