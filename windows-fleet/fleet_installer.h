#ifndef STEADDESK_FLEET_INSTALLER_H
#define STEADDESK_FLEET_INSTALLER_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* No Windows handles, exceptions, paths from manifests, credentials or command
 * strings cross this ABI. */
typedef struct SdFleetLease SdFleetLease;
typedef struct SdFleetExpected {
  const uint16_t
      *artifact_leaf; /* NUL terminated UTF-16, fixed private directory only */
  uint64_t size_bytes;
  uint64_t version_code; /* resource tuple must be exactly 1.5.0.N, N ==
                            version_code */
  uint8_t artifact_sha256[32];
  uint8_t signer_cert_sha256[32];
  uint8_t payload_sha256[32]; /* prepare ignores input; readback uses durable
                                 lease-derived binding */
  uint32_t architecture; /* 1 x64; other architectures currently fail closed */
} SdFleetExpected;
typedef struct SdFleetResult {
  uint32_t exit_code; /* 0 vs 3010 vs actual failure; never inferred from launch
                         alone */
  uint32_t process_id;
  uint64_t process_created; /* Windows FILETIME */
} SdFleetResult;
typedef struct SdFleetService {
  uint64_t version_code;
  uint32_t process_id;
  uint32_t running;
  uint64_t process_created;
  uint8_t binary_sha256[32];
} SdFleetService;
enum SdFleetStatus {
  SD_FLEET_OK = 0,
  SD_FLEET_ARGUMENT = 1,
  SD_FLEET_PATH = 2,
  SD_FLEET_ACL = 3,
  SD_FLEET_TRUST = 4,
  SD_FLEET_HASH = 5,
  SD_FLEET_PRODUCT = 6,
  SD_FLEET_VERSION = 7,
  SD_FLEET_SERVICE = 8,
  SD_FLEET_LAUNCH = 9,
  SD_FLEET_WAIT = 10,
  SD_FLEET_MSI_NOT_APPROVED = 11,
  SD_FLEET_ALREADY_LAUNCHED = 12,
  SD_FLEET_PAYLOAD_UNPROVEN = 13
};
/* Capacity counts UTF-16 code units incl NUL. Uses fixed
 * ProgramData\\SteadDesk\\fleet-update. */
uint32_t sd_fleet_private_directory(uint16_t *output, size_t capacity);
uint32_t sd_fleet_prepare(const SdFleetExpected *expected,
                          SdFleetLease **output);
/* Retain lease until this returns, including failed launch or unknown wait. No
 * self elevation. */
uint32_t sd_fleet_launch(SdFleetLease *lease, SdFleetResult *result);
void sd_fleet_release(SdFleetLease *lease);
uint32_t sd_fleet_payload_digest(const SdFleetLease *lease, uint8_t output[32]);
uint32_t sd_fleet_os_version(uint32_t *major);
/* SHA-256(kernel boot-environment GUID), first 64 bits. Never derived from wall
 * time. */
uint32_t sd_fleet_boot_id(uint64_t *boot_id);
#ifdef SD_FLEET_TEST_BUILD
/* Standalone isolated fixture only; production never exports this gate bypass.
 */
uint32_t sd_fleet_test_prepare(const SdFleetExpected *expected,
                               SdFleetLease **output);
#endif
/* Prove both own merchant and the existing fixed-path Mesh Agent are live
 * before committing. */
uint32_t sd_fleet_local_gates(void);
/* expected_prior_pid/created must be persisted before install; require a
 * replacement process. */
uint32_t sd_fleet_readback(const SdFleetExpected *expected, uint32_t prior_pid,
                           uint64_t prior_created, SdFleetService *result);
/* Existing identity snapshot for durable baseline facts; target build need not
 * match yet. */
uint32_t sd_fleet_current_service(SdFleetService *result);
#ifdef __cplusplus
}
#include <string_view>
namespace sd_fleet_policy {
/* Portable admission checks used by the real Windows handle-opening path. */
inline wchar_t upper_ascii(wchar_t c) {
  return c >= L'a' && c <= L'z' ? c - (L'a' - L'A') : c;
}
inline bool local_absolute_path(std::wstring_view p) {
  if (p.size() < 3 || p.size() >= 32000 ||
      !((p[0] >= L'A' && p[0] <= L'Z') || (p[0] >= L'a' && p[0] <= L'z')) ||
      p[1] != L':' || p[2] != L'\\' || p.find(L'/') != p.npos ||
      p.find(L':', 2) != p.npos)
    return false;
  if (p.size() == 3)
    return true;
  size_t at = 3;
  while (at < p.size()) {
    size_t end = p.find(L'\\', at);
    if (end == p.npos)
      end = p.size();
    auto part = p.substr(at, end - at);
    if (part.empty() || part == L"." || part == L".." || part.back() == L'.' ||
        part.back() == L' ')
      return false;
    if (end == p.size())
      return true;
    at = end + 1;
    if (at == p.size())
      return false;
  }
  return false;
}
inline int artifact_kind(std::wstring_view value) {
  if (value.size() <= 4 || value.size() > 128 || value.front() == L'.' ||
      value.back() == L'.' || value.find(L"..") != value.npos)
    return 0;
  for (wchar_t c : value)
    if (!((c >= L'A' && c <= L'Z') || (c >= L'a' && c <= L'z') ||
          (c >= L'0' && c <= L'9') || c == L'.' || c == L'_' || c == L'-'))
      return 0;
  auto end = value.find(L'.');
  auto stem = value.substr(0, end);
  wchar_t name[5]{};
  if (stem.size() <= 4) {
    for (size_t i = 0; i < stem.size(); i++)
      name[i] = upper_ascii(stem[i]);
    std::wstring_view n(name, stem.size());
    if (n == L"CON" || n == L"PRN" || n == L"AUX" || n == L"NUL" ||
        (n.size() == 4 &&
         (n.substr(0, 3) == L"COM" || n.substr(0, 3) == L"LPT") &&
         n[3] >= L'1' && n[3] <= L'9'))
      return 0;
  }
  auto ext = value.substr(value.size() - 4);
  wchar_t normalized[4];
  for (size_t i = 0; i < 4; i++)
    normalized[i] = upper_ascii(ext[i]);
  std::wstring_view e(normalized, 4);
  return e == L".EXE" ? 1 : e == L".MSI" ? 2 : 0;
}
} // namespace sd_fleet_policy
#endif
#endif
