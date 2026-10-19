# NovaDial + Ava007 Rotary Selector Integration

This directory contains the Ava007 rotary selector component adapted for NovaDial's Kotlin package namespace.

## Scope
- The selector is display-only and cycles through PRIME, SELECT, and ULTRA.
- It does not modify number entry, call placement, SIM selection, contacts, call history, or Telecom behavior.
- The upstream `dhilipmpms/NovaDial` repository is read-only to this account; this integration is staged in MA-Edge-Computing.

## Integration point
In NovaDial, add `Ava007RotarySelectorView` to `app/src/main/res/layout/activity_dialpad.xml` or the dialpad host layout, positioned as a visual header above the existing numeric keypad. Keep the existing keypad views and their IDs intact so `DialpadActivity` continues to own number entry and calling.

Use the fully qualified custom view name:

```xml
<com.novadial.phone.views.Ava007RotarySelectorView
    android:id="@+id/ava007RotarySelector"
    android:layout_width="240dp"
    android:layout_height="282dp" />
```

Place it within the existing layout's constraints/parent rules. Do not replace or rename the existing `dialpad_0` through `dialpad_9`, plus, star, or hash views.

## Verification still required
This is a component staging commit, not a complete NovaDial port or a verified APK. The full NovaDial source tree must be brought into a writable repository before the layout can be integrated and the Android build run.
