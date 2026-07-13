import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class EliteTheme {
  static const seed      = Color(0xFF1B7A6B);   // deep teal
  static const _gold     = Color(0xFFD4A843);   // warm gold accent
  static const _darkBg   = Color(0xFF0D1117);
  static const _darkCard = Color(0xFF161B22);
  static const _darkSurf = Color(0xFF1C2330);

  static ThemeData light() => _base(Brightness.light);
  static ThemeData dark()  => _base(Brightness.dark);

  static TextTheme _textTheme(ColorScheme scheme) {
    // Cairo — excellent Arabic readability, modern feel
    final base = GoogleFonts.cairoTextTheme().apply(
      bodyColor: scheme.onSurface,
      displayColor: scheme.onSurface,
    );
    return base.copyWith(
      displayLarge:  base.displayLarge?.copyWith(fontWeight: FontWeight.w700, fontSize: 32),
      displayMedium: base.displayMedium?.copyWith(fontWeight: FontWeight.w700, fontSize: 26),
      headlineLarge: base.headlineLarge?.copyWith(fontWeight: FontWeight.w700, fontSize: 22),
      headlineMedium:base.headlineMedium?.copyWith(fontWeight: FontWeight.w600, fontSize: 18),
      titleLarge:    base.titleLarge?.copyWith(fontWeight: FontWeight.w600, fontSize: 17),
      titleMedium:   base.titleMedium?.copyWith(fontWeight: FontWeight.w600, fontSize: 15),
      titleSmall:    base.titleSmall?.copyWith(fontWeight: FontWeight.w500, fontSize: 13),
      bodyLarge:     base.bodyLarge?.copyWith(fontWeight: FontWeight.w400, fontSize: 15, height: 1.7),
      bodyMedium:    base.bodyMedium?.copyWith(fontWeight: FontWeight.w400, fontSize: 14, height: 1.6),
      bodySmall:     base.bodySmall?.copyWith(fontWeight: FontWeight.w400, fontSize: 12, height: 1.5),
      labelLarge:    base.labelLarge?.copyWith(fontWeight: FontWeight.w600, fontSize: 14),
      labelMedium:   base.labelMedium?.copyWith(fontWeight: FontWeight.w500, fontSize: 12),
      labelSmall:    base.labelSmall?.copyWith(fontWeight: FontWeight.w500, fontSize: 11),
    );
  }

  static ThemeData _base(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final scheme = isDark
        ? ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.dark).copyWith(
            surface: _darkBg,
            surfaceContainerLowest: _darkBg,
            surfaceContainerLow:    _darkCard,
            surfaceContainer:       _darkCard,
            surfaceContainerHigh:   _darkSurf,
            surfaceContainerHighest:_darkSurf,
            secondary: _gold,
            onSecondary: Colors.black,
          )
        : ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.light).copyWith(
            secondary: _gold,
            onSecondary: Colors.black,
          );

    final textTheme = _textTheme(scheme);

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      textTheme: textTheme,
      scaffoldBackgroundColor: scheme.surface,

      appBarTheme: AppBarTheme(
        centerTitle: true,
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 1,
        shadowColor: scheme.outlineVariant.withValues(alpha: 0.3),
        titleTextStyle: textTheme.titleLarge?.copyWith(
          color: scheme.onSurface,
          fontWeight: FontWeight.w700,
        ),
      ),

      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(
            color: scheme.outlineVariant.withValues(alpha: isDark ? 0.3 : 0.15),
            width: 1,
          ),
        ),
      ),

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: textTheme.labelLarge?.copyWith(fontSize: 15),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          side: BorderSide(color: scheme.outline.withValues(alpha: 0.4)),
          textStyle: textTheme.labelLarge?.copyWith(fontSize: 15),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: textTheme.labelLarge,
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest.withValues(alpha: isDark ? 0.5 : 0.4),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(
            color: scheme.outlineVariant.withValues(alpha: 0.25),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.primary, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        hintStyle: textTheme.bodyMedium?.copyWith(
          color: scheme.onSurfaceVariant.withValues(alpha: 0.6),
        ),
      ),

      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        side: BorderSide.none,
        labelStyle: textTheme.labelMedium,
      ),

      tabBarTheme: TabBarThemeData(
        labelStyle: textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
        unselectedLabelStyle: textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w500),
        indicatorSize: TabBarIndicatorSize.tab,
        dividerColor: scheme.outlineVariant.withValues(alpha: 0.2),
      ),

      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant.withValues(alpha: 0.2),
        thickness: 1,
        space: 1,
      ),

      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: scheme.surface,
        selectedItemColor: scheme.primary,
        unselectedItemColor: scheme.onSurfaceVariant,
        type: BottomNavigationBarType.fixed,
        selectedLabelStyle: textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w600),
        unselectedLabelStyle: textTheme.labelSmall,
        elevation: 0,
      ),

      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surface,
        indicatorColor: scheme.primaryContainer,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return textTheme.labelSmall?.copyWith(
              color: scheme.primary,
              fontWeight: FontWeight.w700,
            );
          }
          return textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant);
        }),
        elevation: 0,
        surfaceTintColor: Colors.transparent,
      ),

      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        contentTextStyle: textTheme.bodyMedium?.copyWith(color: Colors.white),
      ),

      dialogTheme: DialogThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        backgroundColor: scheme.surfaceContainerHigh,
        titleTextStyle: textTheme.headlineMedium?.copyWith(color: scheme.onSurface),
        contentTextStyle: textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
      ),
    );
  }
}
