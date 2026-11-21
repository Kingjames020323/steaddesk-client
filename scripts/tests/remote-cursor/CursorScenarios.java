package com.carriez.flutter_hbb;

public final class CursorScenarios {
    static void equal(float expected, float actual) {
        if (Math.abs(expected - actual) > 0.001f) {
            throw new AssertionError("expected " + expected + ", got " + actual);
        }
    }

    static void point(int frameWidth, int frameHeight, int scale,
                      int x, int y, int expectedX, int expectedY) {
        equal(expectedX, RemoteCursorState.physicalCoordinate(x, frameWidth, scale));
        equal(expectedY, RemoteCursorState.physicalCoordinate(y, frameHeight, scale));
    }

    public static void main(String[] args) {
        // Android rotates the capture before encoding. 90/270 use landscape dimensions,
        // 0/180 use portrait; at any rotation the top-left of the received image is (0,0).
        point(1080, 1920, 1, 1079, 1919, 1079, 1919);
        point(1920, 1080, 1, 1500, 940, 1500, 940);
        point(540, 960, 2, 383, 600, 766, 1200);
        point(960, 540, 2, 835, 123, 1670, 246);
        point(960, 540, 2, 1000, -1, 1918, 0);
        point(0, 0, 2, 12, 10, 0, 0);
        RemoteCursorState cursor = new RemoteCursorState();
        equal(0, cursor.opacity(0));
        cursor.move(10, 40, false, 100);
        equal(1, cursor.opacity(100));
        equal(1, cursor.clickProgress(100));
        cursor.move(85, 40, true, 600);
        equal(85, cursor.x);
        equal(40, cursor.y);
        equal(0, cursor.clickProgress(600));
        equal(0.5f, cursor.clickProgress(760));
        equal(1, cursor.clickProgress(920));
        equal(1, cursor.opacity(5600));
        equal(0.5f, cursor.opacity(5720));
        equal(0, cursor.opacity(5840));
        cursor.move(55, 70, false, 9000);
        equal(1, cursor.opacity(9000));
        equal(1, cursor.clickProgress(9000));
    }
}
