import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models.dart';
import '../state/auth_controller.dart';
import '../widgets/character_widget.dart';
import '../widgets/common.dart';

/// Character/skin store — browse and purchase skins with XP.
class StoreScreen extends StatefulWidget {
  const StoreScreen({super.key});

  @override
  State<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends State<StoreScreen> {
  bool _loading = true;
  String? _error;
  List<StoreSkin> _skins = [];
  int _xp = 0;
  String? _gender;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = context.read<AuthController>().api;
      final results = await Future.wait([
        api.storeSkins(),
        api.me('first'),
      ]);
      if (!mounted) return;
      setState(() {
        _skins = results[0] as List<StoreSkin>;
        final profile = results[1] as Profile;
        _xp = profile.xp;
        _gender = profile.gender;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _selectGender() async {
    final picked = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('اختر جنسك'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Text('👨‍🎓', style: TextStyle(fontSize: 28)),
            title: const Text('ذكر'),
            onTap: () => Navigator.of(_).pop('male'),
          ),
          ListTile(
            leading: const Text('👩‍🎓', style: TextStyle(fontSize: 28)),
            title: const Text('أنثى'),
            onTap: () => Navigator.of(_).pop('female'),
          ),
        ]),
      ),
    );
    if (picked == null || !mounted) return;
    try {
      await context.read<AuthController>().api.setGender(picked);
      if (mounted) await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _buy(StoreSkin skin) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('شراء ${skin.nameAr}'),
        content: Text('سيُخصم ${skin.priceXp} XP من رصيدك (${_xp} XP).\nهل تريد المتابعة؟'),
        actions: [
          TextButton(onPressed: () => Navigator.of(_).pop(false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.of(_).pop(true), child: const Text('اشترِ')),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    try {
      await context.read<AuthController>().api.buySkin(skin.id);
      await _equip(skin.id);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _equip(int skinId) async {
    try {
      await context.read<AuthController>().api.equipSkin(skinId);
      if (mounted) await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('متجر الشخصيات')),
      body: _loading
          ? const Loading()
          : _error != null
              ? ErrorView(_error!, onRetry: _load)
              : Column(
                  children: [
                    // XP balance + gender banner
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                      child: Row(children: [
                        Expanded(
                          child: Card(
                            color: scheme.primaryContainer,
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              child: Row(children: [
                                Icon(Icons.stars, color: scheme.onPrimaryContainer),
                                const SizedBox(width: 8),
                                Text('$_xp XP',
                                    style: TextStyle(
                                        fontWeight: FontWeight.bold,
                                        color: scheme.onPrimaryContainer,
                                        fontSize: 16)),
                              ]),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        SizedBox(
                          width: 120,
                          child: OutlinedButton(
                            onPressed: _selectGender,
                            child: Row(mainAxisSize: MainAxisSize.min, children: [
                              Text(_gender == 'female' ? '👩‍🎓' : '👨‍🎓'),
                              const SizedBox(width: 4),
                              Flexible(child: Text(
                                _gender == null ? 'حدِّد جنسك' : (_gender == 'female' ? 'أنثى' : 'ذكر'),
                                overflow: TextOverflow.ellipsis,
                              )),
                            ]),
                          ),
                        ),
                      ]),
                    ),
                    Expanded(
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final cols = (constraints.maxWidth / 180).floor().clamp(2, 5);
                          return GridView.builder(
                        padding: const EdgeInsets.all(16),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: cols,
                          mainAxisSpacing: 12,
                          crossAxisSpacing: 12,
                          childAspectRatio: 0.85,
                        ),
                        itemCount: _skins.length,
                        itemBuilder: (_, i) => _SkinCard(
                          skin: _skins[i],
                          xp: _xp,
                          onBuy: () => _buy(_skins[i]),
                          onEquip: () => _equip(_skins[i].id),
                        ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
    );
  }
}

class _SkinCard extends StatelessWidget {
  final StoreSkin skin;
  final int xp;
  final VoidCallback onBuy;
  final VoidCallback onEquip;

  const _SkinCard({
    required this.skin,
    required this.xp,
    required this.onBuy,
    required this.onEquip,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final canAfford = xp >= skin.priceXp;

    // Build a SkinInfo from StoreSkin for CharacterWidget
    final skinInfo = SkinInfo(
      id: skin.id,
      nameAr: skin.nameAr,
      emoji: skin.emoji,
      bgColor: skin.bgColor,
    );

    return Card(
      elevation: skin.active ? 4 : 1,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: skin.active
            ? BorderSide(color: scheme.primary, width: 2)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CharacterWidget(skin: skinInfo, size: 80),
            const SizedBox(height: 8),
            Text(skin.nameAr,
                style: const TextStyle(fontWeight: FontWeight.bold),
                textAlign: TextAlign.center),
            const SizedBox(height: 4),
            if (skin.priceXp == 0)
              Text('مجاني', style: TextStyle(color: scheme.primary, fontSize: 12))
            else
              Text('${skin.priceXp} XP',
                  style: TextStyle(
                      color: canAfford ? scheme.secondary : scheme.error,
                      fontSize: 12,
                      fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            if (skin.active)
              Chip(
                label: const Text('مُفعَّل', style: TextStyle(fontSize: 11)),
                backgroundColor: scheme.primaryContainer,
              )
            else if (skin.owned)
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: onEquip,
                  style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 4)),
                  child: const Text('تفعيل', style: TextStyle(fontSize: 12)),
                ),
              )
            else
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: canAfford ? onBuy : null,
                  style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 4)),
                  child: Text(canAfford ? 'اشترِ' : 'XP غير كافٍ',
                      style: const TextStyle(fontSize: 11)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
