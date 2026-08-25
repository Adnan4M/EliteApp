import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models.dart';

/// Renders a character avatar from the Word Atlas design set.
/// The character is chosen by [skin.id] (1–15). Falls back to #1 (Scientist).
class CharacterWidget extends StatelessWidget {
  final SkinInfo? skin;
  final String? gender;
  final double size;

  const CharacterWidget({super.key, this.skin, this.gender, this.size = 56});

  @override
  Widget build(BuildContext context) {
    final type = skin?.emoji ?? 'scientist';
    return SizedBox(
      width: size,
      height: size,
      child: FittedBox(
        fit: BoxFit.contain,
        child: SizedBox(width: 64, height: 64, child: _build(type)),
      ),
    );
  }

  Widget _build(String type) {
    switch (type) {
      case 'star':       return const _StarChar();
      case 'atom':       return const _AtomChar();
      case 'planet':     return const _PlanetChar();
      case 'cell':       return const _CellChar();
      case 'molecule':   return const _MoleculeChar();
      case 'dna':        return const _DnaChar();
      case 'crystal':    return const _CrystalChar();
      case 'galaxy':     return const _GalaxyChar();
      case 'fossil':     return const _FossilChar();
      case 'element':    return const _ElementChar();
      case 'microscope': return const _MicroscopeChar();
      case 'compass':    return const _CompassChar();
      case 'energy':     return const _EnergyChar();
      case 'ecosystem':  return const _EcosystemChar();
      default:           return const _ScientistChar();
    }
  }
}

// ── Shared palette ─────────────────────────────────────────────────────────────
const _skin  = Color(0xFFF7F2E6);
const _dark  = Color(0xFF2A2A28);
const _mouth = Color(0xFFA5764F);

// ── Shared helpers ─────────────────────────────────────────────────────────────

Widget _circle(double s, Color c) => Container(
  width: s, height: s,
  decoration: BoxDecoration(shape: BoxShape.circle, color: c),
);

Widget _ring(double s, Color c, {double w = 1.5}) => Container(
  width: s, height: s,
  decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c, width: w)),
);

Widget _rect(double w, double h, Color c, {BorderRadius? r}) => Container(
  width: w, height: h,
  decoration: BoxDecoration(color: c, borderRadius: r),
);

// face at 64-px coordinate space: top:14, centered (left:19), 26×26
Widget _standardFace({bool glasses = false, Color? glassColor}) {
  final gc = glassColor ?? const Color(0xFF3A2352);
  return Container(
    width: 26, height: 26,
    decoration: const BoxDecoration(shape: BoxShape.circle, color: _skin),
    child: Stack(clipBehavior: Clip.none, children: [
      if (glasses) ...[
        Positioned(top: 8, left: 1,  child: _ring(9, gc, w: 2)),
        Positioned(top: 8, right: 1, child: _ring(9, gc, w: 2)),
        Positioned(top: 12, left: 8, child: _rect(4, 2, gc)),
        Positioned(top: 11, left: 4,  child: _circle(3, _dark)),
        Positioned(top: 11, right: 4, child: _circle(3, _dark)),
        Positioned(top: 19, left: 8, child: _mouthArc(9)),
      ] else ...[
        Positioned(top: 11, left: 6,  child: _circle(3, _dark)),
        Positioned(top: 11, right: 6, child: _circle(3, _dark)),
        Positioned(top: 17, left: 9,  child: _mouthArc(8)),
      ],
    ]),
  );
}

Widget _mouthArc(double w) => Container(
  width: w, height: 3,
  decoration: BoxDecoration(
    border: const Border(bottom: BorderSide(color: _mouth, width: 1.5)),
    borderRadius: BorderRadius.circular(8),
  ),
);

// Common body (white rounded bottom)
Widget _body(double w) => Positioned(
  bottom: -6, left: (64 - w) / 2,
  child: Container(
    width: w, height: 34,
    decoration: const BoxDecoration(
      color: _skin,
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
  ),
);

// Face (white circle) — centered at x=32, top=14
Widget _face({bool glasses = false, Color? glassColor}) => Positioned(
  top: 14, left: 19,
  child: _standardFace(glasses: glasses, glassColor: glassColor),
);

// Badge container bottom-right outside the circle
Widget _badge(Color bg, Color border, Widget child) => Positioned(
  bottom: -2, right: -2,
  child: Container(
    width: 22, height: 22,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: Colors.white,
      border: Border.all(color: border, width: 2),
    ),
    alignment: Alignment.center,
    child: child,
  ),
);

// Base: ClipOval avatar circle + layers + badge
Widget _avatar({
  required Color bg,
  required List<Widget> layers,
  required Widget badge,
  bool faceLast = false,
  bool glasses = false,
  Color? glassColor,
}) {
  final faceWidget = _face(glasses: glasses, glassColor: glassColor);
  final bodyWidget = _body(48);
  final inner = faceLast
      ? [...layers, bodyWidget, faceWidget]
      : [bodyWidget, ...layers, faceWidget];

  return Stack(clipBehavior: Clip.none, children: [
    ClipOval(
      child: Container(
        width: 64, height: 64, color: bg,
        child: Stack(clipBehavior: Clip.none, children: inner),
      ),
    ),
    badge,
  ]);
}

// ── Star clip-path helper ───────────────────────────────────────────────────────
const _starPts = [
  Offset(0.50, 0.00), Offset(0.61, 0.35), Offset(0.98, 0.35),
  Offset(0.68, 0.57), Offset(0.79, 0.91), Offset(0.50, 0.70),
  Offset(0.21, 0.91), Offset(0.32, 0.57), Offset(0.02, 0.35),
  Offset(0.39, 0.35),
];

class _PolygonClipper extends CustomClipper<Path> {
  final List<Offset> pts;
  const _PolygonClipper(this.pts);
  @override Path getClip(Size s) {
    final path = Path()..moveTo(pts[0].dx * s.width, pts[0].dy * s.height);
    for (final p in pts.skip(1)) path.lineTo(p.dx * s.width, p.dy * s.height);
    return path..close();
  }
  @override bool shouldReclip(_) => false;
}

Widget _starShape(double w, double h, Color c) => ClipPath(
  clipper: const _PolygonClipper(_starPts),
  child: Container(width: w, height: h, color: c),
);

// Lightning bolt: polygon(60% 0%, 10% 55%, 45% 55%, 35% 100%, 90% 40%, 55% 40%)
const _boltPts = [
  Offset(0.60, 0.00), Offset(0.10, 0.55), Offset(0.45, 0.55),
  Offset(0.35, 1.00), Offset(0.90, 0.40), Offset(0.55, 0.40),
];

Widget _bolt(double w, double h, Color c) => ClipPath(
  clipper: const _PolygonClipper(_boltPts),
  child: Container(width: w, height: h, color: c),
);

// Crystal pentagon: polygon(50% 0%,100% 40%,80% 100%,20% 100%,0% 40%)
const _crystalPts = [
  Offset(0.50, 0.00), Offset(1.00, 0.40), Offset(0.80, 1.00),
  Offset(0.20, 1.00), Offset(0.00, 0.40),
];

Widget _crystal(double w, double h, Color c) => ClipPath(
  clipper: const _PolygonClipper(_crystalPts),
  child: Container(width: w, height: h, color: c),
);

// Galaxy swirl: polygon(50% 0%,60% 60%,100% 50%,50% 100%,40% 40%,0% 50%)
const _galaxyPts = [
  Offset(0.50, 0.00), Offset(0.60, 0.60), Offset(1.00, 0.50),
  Offset(0.50, 1.00), Offset(0.40, 0.40), Offset(0.00, 0.50),
];

Widget _galaxyShape(double w, double h, Color c) => ClipPath(
  clipper: const _PolygonClipper(_galaxyPts),
  child: Container(width: w, height: h, color: c),
);

// Leaf shape helper using BorderRadius
Widget _leaf(double w, double h, Color c, {bool flip = false}) => Container(
  width: w, height: h,
  decoration: BoxDecoration(
    color: c,
    borderRadius: flip
        ? const BorderRadius.only(topRight: Radius.circular(100), bottomLeft: Radius.circular(100))
        : const BorderRadius.only(topLeft: Radius.circular(100), bottomRight: Radius.circular(100)),
  ),
);

// ── 01 Scientist ──────────────────────────────────────────────────────────────
class _ScientistChar extends StatelessWidget {
  const _ScientistChar();
  @override
  Widget build(BuildContext context) {
    const bg = Color(0xFFC62F2F);
    const grey = Color(0xFF9AA3AD);
    const lens = Color(0xFF2A2A28);
    return _avatar(
      bg: bg,
      layers: [
        // Helmet grey bubbles
        Positioned(top: 4,  left: 25, child: _circle(13, grey)),
        Positioned(top: 7,  left: 19, child: _circle(12, grey)),
        Positioned(top: 7,  left: 33, child: _circle(12, grey)),
        Positioned(top: 13, left: 11, child: _circle(15, grey)),
        Positioned(top: 13, left: 38, child: _circle(15, grey)),
        // Lenses
        Positioned(top: 24, left: 21, child: _ring(10, lens, w: 2)),
        Positioned(top: 24, left: 33, child: _ring(10, lens, w: 2)),
        // Pupils
        Positioned(top: 28, left: 25, child: _circle(3, lens)),
        Positioned(top: 28, left: 36, child: _circle(3, lens)),
        // Nose bridge
        Positioned(top: 28, left: 29, child: _rect(5, 2, lens)),
      ],
      badge: _badge(bg, Colors.white, _badgeFlask(bg)),
    );
  }
  Widget _badgeFlask(Color c) => Stack(children: [
    Positioned(top: 0, left: 4, child: _rect(4, 5, c)),
    ClipPath(
      clipper: const _PolygonClipper([
        Offset(0.30, 0), Offset(0.70, 0), Offset(1, 1), Offset(0, 1)
      ]),
      child: Container(width: 12, height: 10, color: c),
    ),
  ]);
}

// ── 02 Star ───────────────────────────────────────────────────────────────────
class _StarChar extends StatelessWidget {
  const _StarChar();
  @override
  Widget build(BuildContext context) {
    const bg  = Color(0xFFC66B2F);
    const gold = Color(0xFFFFD93D);
    const body = Color(0xFF3B2F57);
    return Stack(clipBehavior: Clip.none, children: [
      ClipOval(
        child: Container(
          width: 64, height: 64, color: bg,
          child: Stack(clipBehavior: Clip.none, children: [
            // Star hat
            Positioned(top: 4, left: 17,
              child: Transform.rotate(angle: -8 * math.pi / 180,
                child: _starShape(30, 30, gold))),
            // Body
            Positioned(bottom: -8, left: 6,
              child: Container(width: 52, height: 32,
                decoration: const BoxDecoration(color: body,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(26))))),
            // Face
            Positioned(bottom: 0, left: 24,
              child: _rect(16, 20, _skin, r: const BorderRadius.vertical(top: Radius.circular(8)))),
            // Star badge on body
            Positioned(bottom: 8, left: 27, child: _starShape(10, 10, gold)),
            // Face circle
            Positioned(top: 18, left: 19,
              child: Container(
                width: 26, height: 26,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFFF0C9A0),
                ),
                child: Stack(children: [
                  Positioned(top: 8, left: 2,
                    child: Container(width:9, height:7,
                      decoration: BoxDecoration(color:const Color(0xFF1B1B1B),
                        borderRadius: BorderRadius.circular(4)))),
                  Positioned(top: 8, right: 2,
                    child: Container(width:9, height:7,
                      decoration: BoxDecoration(color:const Color(0xFF1B1B1B),
                        borderRadius: BorderRadius.circular(4)))),
                  Positioned(top: 18, left: 7,
                    child: Container(width:11, height:6,
                      decoration: BoxDecoration(color:const Color(0xFF8C4A3A),
                        borderRadius: const BorderRadius.vertical(bottom: Radius.circular(11))))),
                  Positioned(top: 16, left: 2,
                    child: Container(width:5, height:3,
                      decoration: BoxDecoration(color:const Color(0xFFE09A7A),
                        borderRadius: BorderRadius.circular(3)))),
                  Positioned(top: 16, right: 2,
                    child: Container(width:5, height:3,
                      decoration: BoxDecoration(color:const Color(0xFFE09A7A),
                        borderRadius: BorderRadius.circular(3)))),
                ]),
              )),
          ]),
        ),
      ),
      _badge(bg, Colors.white, SizedBox(
        width: 8, height: 14,
        child: Stack(children: [
          Positioned(top:0, child: Container(width:8, height:9,
            decoration: BoxDecoration(color:bg, borderRadius:BorderRadius.circular(4)))),
          Positioned(bottom:0, left:3, child: _rect(2, 5, bg)),
          Positioned(bottom:0, child: _rect(8, 2, bg, r: BorderRadius.circular(1))),
        ]),
      )),
    ]);
  }
}

// ── 03 Atom ───────────────────────────────────────────────────────────────────
class _AtomChar extends StatelessWidget {
  const _AtomChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFFC6A82F);
    const dark = Color(0xFF7A5F0F);
    return _avatar(
      bg: bg,
      layers: [
        // Hat
        Positioned(top: 6, left: 18,
          child: Container(width: 28, height: 14,
            decoration: BoxDecoration(color: dark,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(14))))),
        // Orbital rings
        Positioned(top: 20, left: 10,
          child: Transform.rotate(angle: -24 * math.pi / 180,
            child: Container(width: 44, height: 14,
              decoration: BoxDecoration(border: Border.all(color: dark, width: 2),
                borderRadius: BorderRadius.circular(50))))),
        Positioned(top: 20, left: 10,
          child: Transform.rotate(angle: 24 * math.pi / 180,
            child: Container(width: 44, height: 14,
              decoration: BoxDecoration(border: Border.all(color: dark, width: 2),
                borderRadius: BorderRadius.circular(50))))),
        // Nucleus dots
        Positioned(top: 18, left: 47, child: _circle(6, dark)),
        Positioned(top: 32, left: 12, child: _circle(5, dark)),
      ],
      badge: _badge(bg, Colors.white, Stack(children: [
        _ring(14, bg, w: 1.5),
        Positioned(top: 5, left: 2, child: _circle(3, bg)),
      ])),
    );
  }
}

// ── 04 Planet ────────────────────────────────────────────────────────────────
class _PlanetChar extends StatelessWidget {
  const _PlanetChar();
  @override
  Widget build(BuildContext context) {
    const bg    = Color(0xFFA8C62F);
    const green = Color(0xFF4A6B12);
    const lgreen = Color(0xFF7FA32A);
    return _avatar(
      bg: bg,
      layers: [
        // Hat
        Positioned(top: 4, left: 17,
          child: Container(width: 30, height: 20,
            decoration: BoxDecoration(color: green,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(15), topRight: Radius.circular(15),
                bottomLeft: Radius.circular(8), bottomRight: Radius.circular(8))))),
        // Highlights on hat
        Positioned(top: 8, left: 23, child: _circle(7, lgreen)),
        Positioned(top: 14, left: 36, child: _circle(5, lgreen)),
        // Ring around planet
        Positioned(top: 22, left: 6,
          child: Transform.rotate(angle: -16 * math.pi / 180,
            child: Container(width: 52, height: 14,
              decoration: BoxDecoration(border: Border.all(color: green, width: 3),
                borderRadius: BorderRadius.circular(50))))),
      ],
      badge: _badge(bg, Colors.white, SizedBox(
        width: 13, height: 13,
        child: Stack(children: [
          Positioned.fill(child: _circle(13, bg)),
          Positioned(top: 5, left: -3,
            child: Transform.rotate(angle: -14 * math.pi / 180,
              child: _rect(19, 3, const Color(0xFFF7F2E6),
                r: BorderRadius.circular(2)))),
        ]),
      )),
    );
  }
}

// ── 05 Cell ───────────────────────────────────────────────────────────────────
class _CellChar extends StatelessWidget {
  const _CellChar();
  @override
  Widget build(BuildContext context) {
    const bg    = Color(0xFF6BC62F);
    const nucleus = Color(0xFF3F7A22);
    const dot   = Color(0xFFA8E07A);
    return _avatar(
      bg: bg,
      layers: [
        // Nucleus blob
        Positioned(top: 2, left: 16, child: _circle(32, nucleus)),
        // Highlights
        Positioned(top: 7, left: 23, child: _circle(6, dot)),
        Positioned(top: 5, left: 37, child: _circle(4, dot)),
        Positioned(top: 12, left: 34, child: _circle(5, dot)),
        // Bottom stripe
        Positioned(top: 44, left: 13,
          child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white,
        Container(width: 14, height: 10,
          decoration: BoxDecoration(border: Border.all(color: bg, width: 1.5),
            borderRadius: BorderRadius.circular(50)),
          child: Align(alignment: Alignment.topLeft,
            child: Padding(padding: const EdgeInsets.all(2), child: _circle(3, bg))))),
    );
  }
}

// ── 06 Molecule ───────────────────────────────────────────────────────────────
class _MoleculeChar extends StatelessWidget {
  const _MoleculeChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFF2FC62F);
    const dark = Color(0xFF1C6B1C);
    return _avatar(
      bg: bg,
      layers: [
        // Connector bar
        Positioned(top: 11, left: 19, child: _rect(26, 3, dark)),
        // Three atoms
        Positioned(top: 2,  left: 25, child: _circle(14, dark)),
        Positioned(top: 10, left: 16, child: _circle(12, dark)),
        Positioned(top: 10, left: 36, child: _circle(12, dark)),
        // Sheen rings
        Positioned(top: 9,  left: 22, child: _ring(8, bg, w: 1.5)),
        Positioned(top: 9,  left: 34, child: _ring(8, bg, w: 1.5)),
        // Belt stripe
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, SizedBox(
        width: 14, height: 10,
        child: Stack(children: [
          Positioned(top: 0, left: 5, child: _circle(5, bg)),
          Positioned(bottom: 0, left: 0, child: _circle(4, bg)),
          Positioned(bottom: 0, right: 0, child: _circle(4, bg)),
        ]),
      )),
    );
  }
}

// ── 07 DNA ────────────────────────────────────────────────────────────────────
class _DnaChar extends StatelessWidget {
  const _DnaChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFF2FC66B);
    const dark = Color(0xFF0F6B3D);
    return _avatar(
      bg: bg,
      layers: [
        // DNA strands (horizontal rungs)
        Positioned(top: 0, left: 19,
          child: Transform.rotate(angle: 14 * math.pi / 180,
            child: _rect(26, 6, dark, r: BorderRadius.circular(3)))),
        Positioned(top: 7, left: 19,
          child: Transform.rotate(angle: -14 * math.pi / 180,
            child: _rect(26, 6, dark, r: BorderRadius.circular(3)))),
        Positioned(top: 14, left: 19,
          child: Transform.rotate(angle: 14 * math.pi / 180,
            child: _rect(26, 6, dark, r: BorderRadius.circular(3)))),
        // Side rings
        Positioned(top: 8, left: 2,  child: _ring(7, bg, w: 1.5)),
        Positioned(top: 8, right: 2, child: _ring(7, bg, w: 1.5)),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, SizedBox(
        width: 10, height: 14,
        child: Stack(children: [
          Positioned(top: 1, child: Transform.rotate(angle: 20*math.pi/180,
            child: _rect(10, 2, bg, r: BorderRadius.circular(1)))),
          Positioned(top: 6, child: Transform.rotate(angle: -20*math.pi/180,
            child: _rect(10, 2, bg, r: BorderRadius.circular(1)))),
          Positioned(top: 11, child: Transform.rotate(angle: 20*math.pi/180,
            child: _rect(10, 2, bg, r: BorderRadius.circular(1)))),
        ]),
      )),
    );
  }
}

// ── 08 Crystal ────────────────────────────────────────────────────────────────
class _CrystalChar extends StatelessWidget {
  const _CrystalChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFF2FC6A8);
    const dark = Color(0xFF12897A);
    const ddark = Color(0xFF0F7568);
    return _avatar(
      bg: bg,
      layers: [
        Positioned(top: 8, left: 17,  child: _crystal(10, 18, dark)),
        Positioned(top: 2, left: 26,  child: _crystal(12, 24, ddark)),
        Positioned(top: 8, left: 37,  child: _crystal(10, 18, dark)),
        // Top crown detail
        ClipPath(
          clipper: const _PolygonClipper([
            Offset(0,1), Offset(0.2,0), Offset(0.5,0.6), Offset(0.8,0), Offset(1,1)
          ]),
          child: Positioned(top: 3, left: 24,
            child: Container(width: 16, height: 10, color: bg)),
        ),
        // Belt
        Positioned(top: 44, left: 26,
          child: Transform.rotate(angle: 45 * math.pi / 180,
            child: _rect(12, 12, bg))),
      ],
      badge: _badge(bg, Colors.white, Transform.rotate(
        angle: 45 * math.pi / 180, child: _rect(12, 12, bg))),
    );
  }
}

// ── 09 Galaxy ─────────────────────────────────────────────────────────────────
class _GalaxyChar extends StatelessWidget {
  const _GalaxyChar();
  @override
  Widget build(BuildContext context) {
    const bg    = Color(0xFF2FA8C6);
    const space = Color(0xFF132C4A);
    const gold  = Color(0xFFFFD93D);
    return _avatar(
      bg: bg,
      layers: [
        // Space cloud hat
        Positioned(top: 5, left: 17,
          child: Container(width: 30, height: 18,
            decoration: BoxDecoration(color: space,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(50), topRight: Radius.circular(50),
                bottomLeft: Radius.circular(40), bottomRight: Radius.circular(40))))),
        // Stars in cloud
        Positioned(top: 9, left: 24, child: _circle(5, gold)),
        Positioned(top: 14, left: 35, child: _circle(3, _skin)),
        Positioned(top: 8, left: 42, child: _circle(4, _skin)),
        // Stars outside cloud
        Positioned(top: 2, right: 2,
          child: _starShape(6, 6, _skin)),
        Positioned(top: 20, left: 0,
          child: _starShape(4, 4, _skin)),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, _galaxyShape(14, 14, bg)),
    );
  }
}

// ── 10 Fossil ─────────────────────────────────────────────────────────────────
class _FossilChar extends StatelessWidget {
  const _FossilChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFF2F6BC6);
    const brown = Color(0xFF6B4A2A);
    const bone  = Color(0xFFECE3CF);
    return _avatar(
      bg: bg,
      layers: [
        // Fossil skull base
        Positioned(top: 6, left: 17,
          child: Container(width: 30, height: 16,
            decoration: BoxDecoration(color: brown,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(50), topRight: Radius.circular(50))))),
        // Bone strip
        Positioned(top: 6, left: 19, child: _rect(26, 7, bone, r: BorderRadius.circular(4))),
        // Bone end circles
        Positioned(top: 3,  left: 17, child: _circle(8, bone)),
        Positioned(top: 9,  left: 17, child: _circle(8, bone)),
        Positioned(top: 3,  right: 17, child: _circle(8, bone)),
        Positioned(top: 9,  right: 17, child: _circle(8, bone)),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, SizedBox(
        width: 14, height: 6,
        child: Stack(children: [
          Positioned.fill(child: _rect(14, 6, bg, r: BorderRadius.circular(3))),
          Positioned(top: -2, left: -2,  child: _circle(5, bg)),
          Positioned(top: -2, right: -2, child: _circle(5, bg)),
        ]),
      )),
    );
  }
}

// ── 11 Element ────────────────────────────────────────────────────────────────
class _ElementChar extends StatelessWidget {
  const _ElementChar();
  @override
  Widget build(BuildContext context) {
    const bg    = Color(0xFF2F2FC6);
    const tile  = Color(0xFF1B2A8A);
    return _avatar(
      bg: bg,
      layers: [
        // Periodic table tile
        Positioned(top: 3, left: 19,
          child: Container(width: 26, height: 20,
            decoration: BoxDecoration(color: tile, borderRadius: BorderRadius.circular(4)),
            alignment: Alignment.center,
            child: const Text('26',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _skin)))),
        // Side squares (eyes of table)
        Positioned(top: 9, left: 22,
          child: Container(width:8, height:8,
            decoration: BoxDecoration(
              color: const Color(0x80FFFFFF),
              border: Border.all(color: bg, width: 1.5),
              borderRadius: BorderRadius.circular(2)))),
        Positioned(top: 9, right: 22,
          child: Container(width:8, height:8,
            decoration: BoxDecoration(
              color: const Color(0x80FFFFFF),
              border: Border.all(color: bg, width: 1.5),
              borderRadius: BorderRadius.circular(2)))),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white,
        const Text('Fe', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: Color(0xFF2F2FC6)))),
    );
  }
}

// ── 12 Microscope ─────────────────────────────────────────────────────────────
class _MicroscopeChar extends StatelessWidget {
  const _MicroscopeChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFF6B2FC6);
    const dark = Color(0xFF3A2352);
    return _avatar(
      bg: bg,
      glasses: true,
      glassColor: dark,
      layers: [
        // Microscope hat
        Positioned(top: 4, left: 17,
          child: Container(width: 30, height: 18,
            decoration: BoxDecoration(color: dark,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(50), topRight: Radius.circular(50),
                bottomLeft: Radius.circular(0), bottomRight: Radius.circular(0))))),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, SizedBox(
        width: 12, height: 14,
        child: Stack(children: [
          Positioned(bottom: 0, child: _rect(12, 3, bg, r: BorderRadius.circular(2))),
          Positioned(bottom: 2, left: 4,
            child: Transform.rotate(angle: 20*math.pi/180, child: _rect(3, 9, bg))),
        ]),
      )),
    );
  }
}

// ── 13 Compass ────────────────────────────────────────────────────────────────
class _CompassChar extends StatelessWidget {
  const _CompassChar();
  @override
  Widget build(BuildContext context) {
    const bg      = Color(0xFFA82FC6);
    const earmuff = Color(0xFF3B2A20);
    const rose    = Color(0xFFF2EAD8);
    return _avatar(
      bg: bg,
      layers: [
        // Earmuffs
        Positioned(top: 11, left: 16,
          child: _rect(9, 12, earmuff, r: BorderRadius.circular(6))),
        Positioned(top: 11, right: 16,
          child: _rect(9, 12, earmuff, r: BorderRadius.circular(6))),
        // Compass rose
        Positioned(top: 0, left: 22,
          child: Container(width: 20, height: 20,
            decoration: BoxDecoration(shape: BoxShape.circle, color: rose,
              border: Border.all(color: const Color(0xFF6B1F7D), width: 2)),
            child: Stack(children: [
              // North arrow (up = purple)
              Positioned(top: 3, left: 7,
                child: _triangle(6, 7, bg)),
              // South arrow (down = dark)
              Positioned(top: 9, left: 7,
                child: Transform.rotate(angle: math.pi,
                  child: _triangle(6, 7, earmuff))),
            ]),
          )),
      ],
      badge: _badge(bg, Colors.white,
        Container(width: 14, height: 14,
          decoration: BoxDecoration(shape: BoxShape.circle,
            border: Border.all(color: bg, width: 1.5)),
          child: Align(alignment: Alignment.topCenter,
            child: Padding(padding: const EdgeInsets.only(top: 2),
              child: _triangle(6, 7, bg))))),
    );
  }

  Widget _triangle(double w, double h, Color c) => CustomPaint(
    size: Size(w, h),
    painter: _TrianglePainter(c),
  );
}

class _TrianglePainter extends CustomPainter {
  final Color color;
  const _TrianglePainter(this.color);
  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..moveTo(size.width / 2, 0)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(path, Paint()..color = color);
  }
  @override bool shouldRepaint(_) => false;
}

// ── 14 Energy ─────────────────────────────────────────────────────────────────
class _EnergyChar extends StatelessWidget {
  const _EnergyChar();
  @override
  Widget build(BuildContext context) {
    const bg   = Color(0xFFC62FA8);
    const gold = Color(0xFFFFD93D);
    return _avatar(
      bg: bg,
      layers: [
        // Central bolt
        Positioned(top: 2, left: 22, child: _bolt(20, 28, gold)),
        // Side bolts
        Positioned(top: 10, left: 12,  child: _bolt(11, 18, gold)),
        Positioned(top: 10, right: 12,
          child: Transform(
            alignment: Alignment.center,
            transform: Matrix4.diagonal3Values(-1, 1, 1),
            child: _bolt(11, 18, gold))),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, _bolt(9, 14, bg)),
    );
  }
}

// ── 15 Ecosystem ──────────────────────────────────────────────────────────────
class _EcosystemChar extends StatelessWidget {
  const _EcosystemChar();
  @override
  Widget build(BuildContext context) {
    const bg    = Color(0xFFC62F6B);
    const dark  = Color(0xFF2F6B28);
    const mid   = Color(0xFF3F8A34);
    const light = Color(0xFF4D7C3A);
    return _avatar(
      bg: bg,
      layers: [
        // Horizontal stem
        Positioned(top: 4, left: 17, child: _rect(30, 6, light, r: BorderRadius.circular(3))),
        // Central leaf
        Positioned(top: 4, left: 24, child: _leaf(16, 14, dark)),
        // Side leaves
        Positioned(top: 8, left: 14,
          child: Transform.rotate(angle: -24*math.pi/180, child: _leaf(16, 12, mid))),
        Positioned(top: 8, right: 14,
          child: Transform.rotate(angle: 24*math.pi/180, child: _leaf(16, 12, mid, flip: true))),
        // Wing leaves top
        Positioned(top: 0, left: 22, child: _leaf(8, 6, light)),
        Positioned(top: 0, right: 22, child: _leaf(8, 6, light, flip: true)),
        // Belt
        Positioned(top: 44, left: 13, child: _rect(38, 5, bg, r: BorderRadius.circular(2))),
      ],
      badge: _badge(bg, Colors.white, _leaf(12, 8, light)),
    );
  }
}
