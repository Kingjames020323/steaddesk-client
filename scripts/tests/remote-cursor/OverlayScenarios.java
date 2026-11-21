package com.carriez.flutter_hbb;

import android.accessibilityservice.AccessibilityService;
import android.os.Handler;
import android.view.WindowManager;

public final class OverlayScenarios {
    static void check(boolean actual) { if (!actual) throw new AssertionError(); }
    public static void main(String[] args) {
        AccessibilityService service = new AccessibilityService();
        RemoteCursorOverlay overlay = new RemoteCursorOverlay(service);
        overlay.move(17, 39, true);
        overlay.move(20, 42, false);
        Handler.drain();
        WindowManager windows = service.windows;
        check(windows.view != null && windows.view.x == 20 && windows.view.clicked);
        check(windows.params.type == WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY);
        check((windows.params.flags & WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE) != 0);
        check((windows.params.flags & WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE) != 0);
        overlay.move(21, 43, false);
        overlay.clear();
        Handler.drain();
        check(windows.view == null);
        overlay.move(22, 44, false);
        Handler.drain();
        check(windows.view != null && windows.view.x == 22 && !windows.view.clicked);
        overlay.dispose();
        overlay.move(0, 0, true);
        Handler.drain();
        check(windows.view == null);
    }
}
