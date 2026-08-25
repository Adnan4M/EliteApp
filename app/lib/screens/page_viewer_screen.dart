import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/common.dart';

/// Full-screen viewer that pages through only the matching result pages,
/// each rendered server-side with the keyword highlighted.
class PageViewerScreen extends StatefulWidget {
  final String query;
  final List<SearchLocation> locations;
  final int initialIndex;

  const PageViewerScreen({
    super.key,
    required this.query,
    required this.locations,
    this.initialIndex = 0,
  });

  @override
  State<PageViewerScreen> createState() => _PageViewerScreenState();
}

class _PageViewerScreenState extends State<PageViewerScreen> {
  late final PageController _pageController =
      PageController(initialPage: widget.initialIndex);
  late int _current = widget.initialIndex;
  final Map<int, Future<List<int>>> _cache = {};

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<List<int>> _image(int index) {
    final loc = widget.locations[index];
    return _cache.putIfAbsent(
      index,
      () => context.read<AuthController>().api.pageImage(
            semester: loc.semester,
            subjectId: loc.subjectId,
            page: loc.page,
            query: widget.query,
          ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = widget.locations[_current];
    return Scaffold(
      appBar: AppBar(
        title: Text('«${widget.query}»'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(28),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              '${loc.subjectName} — صفحة ${loc.printed} (${loc.occurrences}×) '
              '· ${_current + 1}/${widget.locations.length}',
              style: Theme.of(context).textTheme.bodySmall,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ),
      body: PageView.builder(
        controller: _pageController,
        itemCount: widget.locations.length,
        onPageChanged: (i) => setState(() => _current = i),
        itemBuilder: (context, i) {
          return FutureBuilder<List<int>>(
            future: _image(widget.locations[i].position),
            builder: (context, snap) {
              if (snap.connectionState == ConnectionState.waiting) {
                return const Loading();
              }
              if (snap.hasError) {
                final isExpired = snap.error.toString().contains('410');
                return ErrorView(
                  isExpired
                      ? 'انتهت صلاحية نتائج البحث. أعد البحث مرة أخرى.'
                      : 'تعذّر تحميل الصفحة',
                  onRetry: () => setState(() {
                    _cache.remove(widget.locations[i].position);
                  }),
                );
              }
              return InteractiveViewer(
                minScale: 1,
                maxScale: 5,
                child: Center(
                    child: Image.memory(
                        Uint8List.fromList(snap.data!),
                        fit: BoxFit.contain)),
              );
            },
          );
        },
      ),
      bottomNavigationBar: BottomAppBar(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            TextButton.icon(
              onPressed: _current > 0
                  ? () => _pageController.previousPage(
                      duration: const Duration(milliseconds: 250),
                      curve: Curves.easeOut)
                  : null,
              icon: const Icon(Icons.chevron_right), // RTL: previous is on the right
              label: const Text('السابق'),
            ),
            TextButton.icon(
              onPressed: _current < widget.locations.length - 1
                  ? () => _pageController.nextPage(
                      duration: const Duration(milliseconds: 250),
                      curve: Curves.easeOut)
                  : null,
              icon: const Icon(Icons.chevron_left),
              label: const Text('التالي'),
            ),
          ],
        ),
      ),
    );
  }
}
