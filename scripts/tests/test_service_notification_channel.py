"""Run the shipped Android channel registration, update receiver and locale resolver on a host JVM."""
import json
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("service-channel")
SRC = Path("flutter/android/app/src/main")
PACKAGE = Path("com/carriez/flutter_hbb")
CHANNEL = SRC / "java" / PACKAGE / "ServiceNotificationChannel.java"
LANGUAGE = SRC / "kotlin" / PACKAGE / "MerchantLanguage.java"
RESOURCES = {
    "en": SRC / "res/values/merchant_language.xml",
    "zh": SRC / "res/values-zh/steaddesk_service.xml",
    "es": SRC / "res/values-es/steaddesk_service.xml",
}


class NotificationChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.tree = Path(temp.name)
        subprocess.run(["git", "init", "-q"], cwd=cls.tree, check=True)
        files = [CHANNEL, LANGUAGE, *RESOURCES.values()]
        for patch in sorted((ROOT / "patches").glob("*.patch")):
            subprocess.run(["git", "apply", *(f"--include={path}" for path in files), patch],
                           cwd=cls.tree, check=True)

        sources = [cls.tree / CHANNEL, cls.tree / LANGUAGE, FIXTURE / "ChannelScenarios.java"]
        for block in (FIXTURE / "platform.java.in").read_text().split("\npackage ")[1:]:
            pkg = block.split(";")[0]
            name = re.search(r"public (?:abstract )?(?:class|@interface) (\w+)", block)[1]
            dest = cls.tree / pkg.replace(".", "/") / (name + ".java")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("package " + block)
            sources.append(dest)
        catalog = cls.tree / "Catalog.java"
        cases = []
        for lang, path in RESOURCES.items():
            strings = ET.parse(cls.tree / path)
            name, description = [
                json.dumps(strings.find(f"string[@name='{key}']").text, ensure_ascii=False)
                for key in ("merchant_channel", "merchant_channel_description")
            ]
            cases.append(f'case "{lang}": return resource == 0 ? {name} : {description};')
        catalog.write_text("package com.carriez.flutter_hbb; class Catalog {"
                           "static String get(String language, int resource) { switch (language) {"
                           + "\n".join(cases) + "default: throw new AssertionError(language); } } }")
        subprocess.run(["javac", "-encoding", "UTF-8", "-d", cls.tree, *sources, catalog], check=True)

    def scenario(self, name):
        subprocess.run(["java", "-cp", self.tree, "com.carriez.flutter_hbb.ChannelScenarios", name],
                       check=True)

    def test_fresh_and_merchant_language_switch(self):
        self.scenario("fresh")

    def test_upgrade_keeps_silent_settings(self):
        self.scenario("muted")

    def test_upgrade_keeps_blocked_channel(self):
        self.scenario("blocked")

    def test_repeated_upgrade_keeps_blocked_branded_channel(self):
        self.scenario("branded")

    def test_app_permission_denied_stays_denied(self):
        self.scenario("denied")

    def test_both_ids_preserve_a_block_on_either(self):
        self.scenario("both")

    def test_support_follows_device_language(self):
        self.scenario("support")

    def test_pre_o_keeps_channelless_behavior(self):
        self.scenario("pre-o")
