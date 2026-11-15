#include "../fleet_installer.h"
#include <cassert>
#include <cstddef>
#include <iostream>
int main() {
  using sd_fleet_policy::artifact_kind;
  using sd_fleet_policy::local_absolute_path;
  unsigned checks = 0;
  for (const auto *path : {L"C:\\", L"C:\\Program Files\\SteadDesk",
                           L"D:\\Private\\fleet-update"}) {
    assert(local_absolute_path(path));
    checks++;
  }
  for (const auto *path :
       {L"\\\\server\\share\\a.exe", L"\\\\?\\C:\\a.exe", L"C:relative",
        L"C:/a", L"1:\\bad", L"C:\\a\\..\\b", L"C:\\a\\.\\b", L"C:\\a\\",
        L"C:\\a \\b", L"C:\\a.\\b", L"C:\\a:stream", L"C:\\\\a"}) {
    assert(!local_absolute_path(path));
    checks++;
  }
  for (const auto *path : {L"SteadDesk-1.5.0.exe", L"TEST.EXE", L"a_b-1.exe"}) {
    assert(artifact_kind(path) == 1);
    checks++;
  }
  assert(artifact_kind(L"approved.msi") == 2);
  checks++;
  for (const auto *path :
       {L"..\\evil.exe", L"evil/evil.exe", L".exe", L"bad.exe ",
        L"bad.exe:stream", L"bad..exe", L"CON.exe", L"prn.x.exe", L"LPT9.exe",
        L"COM1.exe", L"NUL.exe", L"x.ps1", L"x.cmd", L"x.exe;whoami",
        L"x.exe\"", L"unicode-试.exe"}) {
    assert(artifact_kind(path) == 0);
    checks++;
  }
  static_assert(sizeof(SdFleetExpected) == 128, "C ABI expected layout drift");
  static_assert(offsetof(SdFleetExpected, payload_sha256) == 88,
                "C ABI payload offset drift");
  static_assert(sizeof(SdFleetResult) == 16, "C ABI process result drift");
  static_assert(sizeof(SdFleetService) == 56, "C ABI service result drift");
  std::cout << "Windows fleet path/ABI checks passed: " << checks << "\n";
}
