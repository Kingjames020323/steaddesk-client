#include "fleet_installer.h"
#define WIN32_LEAN_AND_MEAN
#include <aclapi.h>
#include <algorithm>
#include <array>
#include <bcrypt.h>
#include <cstring>
#include <cwctype>
#include <memory>
#include <sddl.h>
#include <shlobj.h>
#include <softpub.h>
#include <string>
#include <tlhelp32.h>
#include <vector>
#include <wincrypt.h>
#include <windows.h>
#include <winternl.h>
#include <wintrust.h>

namespace {
struct Failure {
  uint32_t status;
};
void need(bool yes, uint32_t status) {
  if (!yes)
    throw Failure{status};
}
struct Handle {
  HANDLE value = INVALID_HANDLE_VALUE;
  Handle() = default;
  explicit Handle(HANDLE h) : value(h) {}
  ~Handle() {
    if (value != INVALID_HANDLE_VALUE && value != nullptr)
      CloseHandle(value);
  }
  Handle(Handle &&h) noexcept : value(h.value) {
    h.value = INVALID_HANDLE_VALUE;
  }
  Handle &operator=(Handle &&h) noexcept {
    if (this != &h) {
      if (value != INVALID_HANDLE_VALUE && value != nullptr)
        CloseHandle(value);
      value = h.value;
      h.value = INVALID_HANDLE_VALUE;
    }
    return *this;
  }
  Handle(const Handle &) = delete;
  Handle &operator=(const Handle &) = delete;
};
struct ServiceHandle {
  SC_HANDLE value = nullptr;
  explicit ServiceHandle(SC_HANDLE h) : value(h) {}
  ~ServiceHandle() {
    if (value)
      CloseServiceHandle(value);
  }
  ServiceHandle(const ServiceHandle &) = delete;
};
struct LocalMemory {
  HLOCAL value = nullptr;
  ~LocalMemory() {
    if (value)
      LocalFree(value);
  }
};
struct CoMemory {
  PWSTR value = nullptr;
  ~CoMemory() {
    if (value)
      CoTaskMemFree(value);
  }
};
#ifdef SD_FLEET_TEST_BUILD
const wchar_t *app_name = L"SteadDeskFleetTest";
const wchar_t *service_name = L"SteadDeskFleetTest";
#else
const wchar_t *app_name = L"SteadDesk";
const wchar_t *service_name = L"SteadDesk";
#endif
uint64_t as_time(FILETIME t) {
  return (uint64_t(t.dwHighDateTime) << 32) | t.dwLowDateTime;
}
std::wstring known(REFKNOWNFOLDERID id) {
  CoMemory p;
  need(
      SUCCEEDED(SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, nullptr, &p.value)) &&
          p.value,
      SD_FLEET_PATH);
  return p.value;
}
std::wstring install_path() {
  return known(FOLDERID_ProgramFiles) + L"\\" + app_name + L"\\SteadDesk.exe";
}
std::wstring staging_path() {
  return known(FOLDERID_ProgramData) + L"\\" + app_name + L"\\fleet-update";
}
bool same_path(const std::wstring &a, const std::wstring &b) {
  return _wcsicmp(a.c_str(), b.c_str()) == 0;
}
std::wstring absolute(const std::wstring &p) {
  need(sd_fleet_policy::local_absolute_path(p), SD_FLEET_PATH);
  DWORD n = GetFullPathNameW(p.c_str(), 0, nullptr, nullptr);
  need(n > 0 && n < 32768, SD_FLEET_PATH);
  std::vector<wchar_t> b(n + 1);
  need(GetFullPathNameW(p.c_str(), DWORD(b.size()), b.data(), nullptr) > 0,
       SD_FLEET_PATH);
  std::wstring out = b.data();
  need(same_path(out, p), SD_FLEET_PATH);
  std::wstring drive = out.substr(0, 3);
  need(GetDriveTypeW(drive.c_str()) == DRIVE_FIXED, SD_FLEET_PATH);
  return out;
}
std::wstring final_path(HANDLE h) {
  std::vector<wchar_t> b(32768);
  DWORD n = GetFinalPathNameByHandleW(h, b.data(), DWORD(b.size()),
                                      FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
  need(n > 0 && n < b.size(), SD_FLEET_PATH);
  std::wstring s(b.data(), n);
  need(s.rfind(L"\\\\?\\", 0) == 0 && s.rfind(L"\\\\?\\UNC\\", 0) != 0,
       SD_FLEET_PATH);
  return s.substr(4);
}
std::vector<uint8_t> current_sid() {
  Handle token;
  HANDLE raw = nullptr;
  need(OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &raw) != 0,
       SD_FLEET_ACL);
  token.value = raw;
  DWORD n = 0;
  GetTokenInformation(token.value, TokenUser, nullptr, 0, &n);
  need(n > 0, SD_FLEET_ACL);
  std::vector<uint8_t> b(n);
  need(GetTokenInformation(token.value, TokenUser, b.data(), n, &n) != 0,
       SD_FLEET_ACL);
  auto user = reinterpret_cast<TOKEN_USER *>(b.data());
  DWORD size = GetLengthSid(user->User.Sid);
  std::vector<uint8_t> sid(size);
  need(CopySid(size, sid.data(), user->User.Sid) != 0, SD_FLEET_ACL);
  return sid;
}
bool well_known(PSID sid, WELL_KNOWN_SID_TYPE type) {
  BYTE b[SECURITY_MAX_SID_SIZE];
  DWORD n = sizeof(b);
  return CreateWellKnownSid(type, nullptr, b, &n) && EqualSid(sid, b);
}
bool trusted_sid(PSID sid, const std::vector<uint8_t> &own) {
  if (EqualSid(sid, const_cast<uint8_t *>(own.data())) ||
      well_known(sid, WinLocalSystemSid) ||
      well_known(sid, WinBuiltinAdministratorsSid))
    return true;
  LocalMemory ti;
  PSID raw = nullptr;
  if (ConvertStringSidToSidW(
          L"S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464",
          &raw)) {
    ti.value = raw;
    return EqualSid(sid, raw) != 0;
  }
  return false;
}
void check_acl(HANDLE h, bool strict) {
  PSECURITY_DESCRIPTOR descriptor = nullptr;
  PACL acl = nullptr;
  PSID owner = nullptr;
  DWORD code = GetSecurityInfo(
      h, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
      &owner, nullptr, &acl, nullptr, &descriptor);
  LocalMemory memory;
  memory.value = descriptor;
  need(code == ERROR_SUCCESS && descriptor && acl && owner, SD_FLEET_ACL);
  auto own = current_sid();
  need(trusted_sid(owner, own), SD_FLEET_ACL);
  // Standard ProgramData ancestors allow creating unrelated child names and
  // attributes. Held no-delete parents plus strict app-owned descendants
  // prevent path replacement.
  const DWORD mutation = WRITE_DAC | WRITE_OWNER | DELETE | FILE_DELETE_CHILD |
                         (strict ? (FILE_WRITE_DATA | FILE_APPEND_DATA |
                                    FILE_WRITE_ATTRIBUTES | FILE_WRITE_EA)
                                 : 0);
  for (DWORD i = 0; i < acl->AceCount; i++) {
    void *p = nullptr;
    need(GetAce(acl, i, &p) != 0, SD_FLEET_ACL);
    auto header = static_cast<ACE_HEADER *>(p);
    if (header->AceFlags & INHERIT_ONLY_ACE)
      continue;
    DWORD mask = 0;
    PSID sid = nullptr;
    if (header->AceType == ACCESS_ALLOWED_ACE_TYPE) {
      auto a = static_cast<ACCESS_ALLOWED_ACE *>(p);
      mask = a->Mask;
      sid = &a->SidStart;
    } else if (header->AceType == ACCESS_DENIED_ACE_TYPE)
      continue;
    else {
      need(header->AceType != ACCESS_ALLOWED_OBJECT_ACE_TYPE &&
               header->AceType != ACCESS_ALLOWED_CALLBACK_ACE_TYPE &&
               header->AceType != ACCESS_ALLOWED_CALLBACK_OBJECT_ACE_TYPE,
           SD_FLEET_ACL);
      continue;
    }
    if (!trusted_sid(sid, own))
      need((mask & (mutation | GENERIC_WRITE | GENERIC_ALL)) == 0,
           SD_FLEET_ACL);
  }
}
Handle open_directory(const std::wstring &p, bool strict) {
  Handle h(CreateFileW(
      p.c_str(), READ_CONTROL | FILE_READ_ATTRIBUTES,
      FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
      FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
  need(h.value != INVALID_HANDLE_VALUE, SD_FLEET_PATH);
  BY_HANDLE_FILE_INFORMATION i{};
  need(GetFileInformationByHandle(h.value, &i) &&
           ((i.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) &&
           !(i.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) &&
           same_path(final_path(h.value), p),
       SD_FLEET_PATH);
  check_acl(h.value, strict);
  return h;
}
std::vector<Handle> lock_directories(const std::wstring &raw,
                                     bool strict_last = true) {
  std::wstring path = absolute(raw);
  std::vector<Handle> out;
  out.push_back(open_directory(path.substr(0, 3), false));
  size_t at = 2;
  for (;;) {
    at = path.find(L'\\', at + 1);
    std::wstring part = at == std::wstring::npos ? path : path.substr(0, at);
    if (part.size() == 2)
      part += L"\\";
    out.push_back(
        open_directory(part, strict_last && at == std::wstring::npos));
    if (at == std::wstring::npos)
      break;
  }
  return out;
}
void mkdir_private(const std::wstring &p) {
  LocalMemory memory;
  PSECURITY_DESCRIPTOR sd = nullptr;
  need(ConvertStringSecurityDescriptorToSecurityDescriptorW(
           L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)", SDDL_REVISION_1, &sd,
           nullptr) != 0,
       SD_FLEET_ACL);
  memory.value = sd;
  SECURITY_ATTRIBUTES sa{sizeof(sa), sd, FALSE};
  if (!CreateDirectoryW(p.c_str(), &sa))
    need(GetLastError() == ERROR_ALREADY_EXISTS, SD_FLEET_PATH);
  auto h = open_directory(p, true);
}
std::vector<Handle> ensure_private() {
  std::wstring base = known(FOLDERID_ProgramData);
  auto parents = lock_directories(base, false);
  std::wstring app = base + L"\\" + app_name;
  mkdir_private(app);
  parents.push_back(open_directory(app, true));
  std::wstring root = app + L"\\fleet-update";
  mkdir_private(root);
  parents.push_back(open_directory(root, true));
  return parents;
}
Handle open_file(const std::wstring &p) {
  Handle h(CreateFileW(p.c_str(), GENERIC_READ | READ_CONTROL, FILE_SHARE_READ,
                       nullptr, OPEN_EXISTING,
                       FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN,
                       nullptr));
  need(h.value != INVALID_HANDLE_VALUE, SD_FLEET_PATH);
  BY_HANDLE_FILE_INFORMATION i{};
  need(GetFileInformationByHandle(h.value, &i) &&
           !(i.dwFileAttributes &
             (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) &&
           i.nNumberOfLinks == 1 && same_path(final_path(h.value), p),
       SD_FLEET_PATH);
  check_acl(h.value, true);
  return h;
}
std::array<uint8_t, 32> hash(HANDLE file, uint64_t *total = nullptr) {
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE state = nullptr;
  need(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr,
                                   0) >= 0,
       SD_FLEET_HASH);
  struct A {
    BCRYPT_ALG_HANDLE h;
    ~A() { BCryptCloseAlgorithmProvider(h, 0); }
  } a{algorithm};
  DWORD n = 0, object_size = 0;
  need(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                         reinterpret_cast<PUCHAR>(&object_size),
                         sizeof(object_size), &n, 0) >= 0,
       SD_FLEET_HASH);
  std::vector<uint8_t> object(object_size);
  need(BCryptCreateHash(algorithm, &state, object.data(), object_size, nullptr,
                        0, 0) >= 0,
       SD_FLEET_HASH);
  struct H {
    BCRYPT_HASH_HANDLE h;
    ~H() { BCryptDestroyHash(h); }
  } s{state};
  LARGE_INTEGER zero{};
  need(SetFilePointerEx(file, zero, nullptr, FILE_BEGIN) != 0, SD_FLEET_HASH);
  std::array<uint8_t, 65536> buffer;
  uint64_t size = 0;
  for (;;) {
    DWORD count = 0;
    need(ReadFile(file, buffer.data(), DWORD(buffer.size()), &count, nullptr) !=
             0,
         SD_FLEET_HASH);
    if (!count)
      break;
    need(size <= UINT64_MAX - count, SD_FLEET_HASH);
    size += count;
    need(BCryptHashData(state, buffer.data(), count, 0) >= 0, SD_FLEET_HASH);
  }
  std::array<uint8_t, 32> result;
  need(BCryptFinishHash(state, result.data(), DWORD(result.size()), 0) >= 0,
       SD_FLEET_HASH);
  if (total)
    *total = size;
  return result;
}
std::array<uint8_t, 32> authenticode(const std::wstring &path, HANDLE file) {
  WINTRUST_FILE_INFO f{};
  f.cbStruct = sizeof(f);
  f.pcwszFilePath = path.c_str();
  f.hFile = file;
  WINTRUST_DATA data{};
  data.cbStruct = sizeof(data);
  data.dwUIChoice = WTD_UI_NONE;
  data.fdwRevocationChecks = WTD_REVOKE_WHOLECHAIN;
  data.dwUnionChoice = WTD_CHOICE_FILE;
  data.pFile = &f;
  data.dwStateAction = WTD_STATEACTION_VERIFY;
  data.dwProvFlags =
      WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT | WTD_DISABLE_MD2_MD4;
  GUID policy = WINTRUST_ACTION_GENERIC_VERIFY_V2;
  LONG status = WinVerifyTrust(nullptr, &policy, &data);
  struct Close {
    WINTRUST_DATA *d;
    GUID *p;
    ~Close() {
      d->dwStateAction = WTD_STATEACTION_CLOSE;
      WinVerifyTrust(nullptr, p, d);
    }
  } close{&data, &policy};
  need(status == ERROR_SUCCESS, SD_FLEET_TRUST);
  auto provider = WTHelperProvDataFromStateData(data.hWVTStateData);
  need(provider != nullptr, SD_FLEET_TRUST);
  auto signer = WTHelperGetProvSignerFromChain(provider, 0, FALSE, 0);
  need(signer && signer->csCertChain > 0 && signer->pasCertChain[0].pCert,
       SD_FLEET_TRUST);
  const auto cert = signer->pasCertChain[0].pCert;
  std::array<uint8_t, 32> fingerprint;
  DWORD size = DWORD(fingerprint.size());
  need(CryptHashCertificate2(BCRYPT_SHA256_ALGORITHM, 0, nullptr,
                             cert->pbCertEncoded, cert->cbCertEncoded,
                             fingerprint.data(), &size) &&
           size == fingerprint.size(),
       SD_FLEET_TRUST);
  return fingerprint;
}
struct Metadata {
  uint64_t build;
  std::array<uint8_t, 32> payload;
  bool payload_present = false;
};
Metadata metadata(const std::wstring &path,
                  const std::array<uint8_t, 32> &fallback) {
  DWORD ignored = 0, size = GetFileVersionInfoSizeW(path.c_str(), &ignored);
  need(size > 0 && size <= 1024 * 1024, SD_FLEET_PRODUCT);
  std::vector<uint8_t> data(size);
  need(GetFileVersionInfoW(path.c_str(), 0, size, data.data()) != 0,
       SD_FLEET_PRODUCT);
  VS_FIXEDFILEINFO *fixed = nullptr;
  UINT n = 0;
  need(VerQueryValueW(data.data(), L"\\", reinterpret_cast<void **>(&fixed),
                      &n) &&
           fixed && n >= sizeof(*fixed) && fixed->dwSignature == 0xfeef04bd,
       SD_FLEET_PRODUCT);
  need(HIWORD(fixed->dwFileVersionMS) == 1 &&
           LOWORD(fixed->dwFileVersionMS) == 5 &&
           HIWORD(fixed->dwFileVersionLS) == 0 &&
           LOWORD(fixed->dwFileVersionLS) > 0 &&
           fixed->dwProductVersionMS == fixed->dwFileVersionMS &&
           fixed->dwProductVersionLS == fixed->dwFileVersionLS,
       SD_FLEET_VERSION);
  struct Translation {
    WORD language, codepage;
  };
  Translation *table = nullptr;
  need(VerQueryValueW(data.data(), L"\\VarFileInfo\\Translation",
                      reinterpret_cast<void **>(&table), &n) &&
           table && n >= sizeof(Translation) && n % sizeof(Translation) == 0,
       SD_FLEET_PRODUCT);
  Metadata result{LOWORD(fixed->dwFileVersionLS), fallback, false};
  bool absent = false;
  for (UINT i = 0; i < n / sizeof(Translation); i++) {
    wchar_t prefix[64];
    swprintf(prefix, 64, L"\\StringFileInfo\\%04x%04x\\", table[i].language,
             table[i].codepage);
    void *value = nullptr;
    UINT count = 0;
    std::wstring product = prefix;
    product += L"ProductName";
    need(VerQueryValueW(data.data(), product.c_str(), &value, &count) &&
             value && count == 10 &&
             std::memcmp(value, L"SteadDesk", 10 * sizeof(wchar_t)) == 0,
         SD_FLEET_PRODUCT);
    std::wstring field = prefix;
    field += L"SteadDeskPayloadSHA256";
    if (VerQueryValueW(data.data(), field.c_str(), &value, &count)) {
      auto text = static_cast<wchar_t *>(value);
      need(count == 65 && text && text[64] == 0, SD_FLEET_PRODUCT);
      std::array<uint8_t, 32> parsed;
      for (size_t j = 0; j < 64; j++) {
        wchar_t c = text[j];
        need((c >= L'0' && c <= L'9') || (c >= L'a' && c <= L'f'),
             SD_FLEET_PRODUCT);
        uint8_t v = uint8_t(c <= L'9' ? c - L'0' : c - L'a' + 10);
        if (j % 2 == 0)
          parsed[j / 2] = uint8_t(v << 4);
        else
          parsed[j / 2] |= v;
      }
      need(!absent && (!result.payload_present || result.payload == parsed),
           SD_FLEET_PRODUCT);
      result.payload = parsed;
      result.payload_present = true;
    } else {
      need(!result.payload_present, SD_FLEET_PRODUCT);
      absent = true;
    }
  }
  return result;
}
void architecture(HANDLE h) {
  LARGE_INTEGER zero{};
  need(SetFilePointerEx(h, zero, nullptr, FILE_BEGIN) != 0, SD_FLEET_PRODUCT);
  IMAGE_DOS_HEADER dos{};
  DWORD n = 0;
  need(ReadFile(h, &dos, sizeof(dos), &n, nullptr) && n == sizeof(dos) &&
           dos.e_magic == IMAGE_DOS_SIGNATURE &&
           dos.e_lfanew >= static_cast<LONG>(sizeof(dos)) &&
           dos.e_lfanew <= 16 * 1024 * 1024,
       SD_FLEET_PRODUCT);
  LARGE_INTEGER offset{};
  offset.QuadPart = dos.e_lfanew;
  need(SetFilePointerEx(h, offset, nullptr, FILE_BEGIN) != 0, SD_FLEET_PRODUCT);
  DWORD signature = 0;
  IMAGE_FILE_HEADER header{};
  need(ReadFile(h, &signature, sizeof(signature), &n, nullptr) &&
           n == sizeof(signature) && signature == IMAGE_NT_SIGNATURE &&
           ReadFile(h, &header, sizeof(header), &n, nullptr) &&
           n == sizeof(header) && header.Machine == IMAGE_FILE_MACHINE_AMD64 &&
           (header.Characteristics & IMAGE_FILE_EXECUTABLE_IMAGE) &&
           !(header.Characteristics & IMAGE_FILE_DLL),
       SD_FLEET_PRODUCT);
}
std::wstring process_path(DWORD pid, uint64_t *created = nullptr) {
  Handle p(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid));
  need(p.value != nullptr && p.value != INVALID_HANDLE_VALUE, SD_FLEET_SERVICE);
  std::vector<wchar_t> b(32768);
  DWORD n = DWORD(b.size());
  need(QueryFullProcessImageNameW(p.value, 0, b.data(), &n) != 0,
       SD_FLEET_SERVICE);
  if (created) {
    FILETIME c, e, k, u;
    need(GetProcessTimes(p.value, &c, &e, &k, &u) != 0, SD_FLEET_SERVICE);
    *created = as_time(c);
  }
  return absolute(std::wstring(b.data(), n));
}
struct ServiceState {
  DWORD pid;
  uint64_t created;
  std::wstring image;
};
std::wstring configured_image(const wchar_t *raw, bool merchant) {
  need(raw && *raw, SD_FLEET_SERVICE);
  std::wstring command = raw;
  need(command.front() == L'"', SD_FLEET_SERVICE);
  size_t end = command.find(L'"', 1);
  need(end != std::wstring::npos, SD_FLEET_SERVICE);
  std::wstring path = absolute(command.substr(1, end - 1));
  std::wstring rest = command.substr(end + 1);
  if (merchant)
    need(rest == L" --service", SD_FLEET_SERVICE);
  return path;
}
ServiceState service(SC_HANDLE manager, const wchar_t *name,
                     const std::wstring &expected, bool merchant) {
  ServiceHandle handle(
      OpenServiceW(manager, name, SERVICE_QUERY_CONFIG | SERVICE_QUERY_STATUS));
  need(handle.value != nullptr, SD_FLEET_SERVICE);
  DWORD bytes = 0;
  QueryServiceConfigW(handle.value, nullptr, 0, &bytes);
  need(bytes > 0 && bytes < 65536, SD_FLEET_SERVICE);
  std::vector<uint8_t> buffer(bytes);
  need(QueryServiceConfigW(
           handle.value,
           reinterpret_cast<QUERY_SERVICE_CONFIGW *>(buffer.data()), bytes,
           &bytes) != 0,
       SD_FLEET_SERVICE);
  auto config = reinterpret_cast<QUERY_SERVICE_CONFIGW *>(buffer.data());
  need(config->dwServiceType == SERVICE_WIN32_OWN_PROCESS &&
           same_path(configured_image(config->lpBinaryPathName, merchant),
                     expected),
       SD_FLEET_SERVICE);
  SERVICE_STATUS_PROCESS status{};
  need(QueryServiceStatusEx(handle.value, SC_STATUS_PROCESS_INFO,
                            reinterpret_cast<LPBYTE>(&status), sizeof(status),
                            &bytes) &&
           status.dwCurrentState == SERVICE_RUNNING && status.dwProcessId > 0,
       SD_FLEET_SERVICE);
  uint64_t created = 0;
  need(same_path(process_path(status.dwProcessId, &created), expected),
       SD_FLEET_SERVICE);
  return {status.dwProcessId, created, expected};
}
ServiceState merchant_service() {
  ServiceHandle manager(OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT));
  need(manager.value != nullptr, SD_FLEET_SERVICE);
  return service(manager.value, service_name, install_path(), true);
}
void agent_running() {
  std::wstring expected = known(FOLDERID_ProgramFiles) +
#ifdef SD_FLEET_TEST_BUILD
                          L"\\SteadDeskFleetTestAgent\\MeshAgent.exe";
#else
                          L"\\Mesh Agent\\MeshAgent.exe";
#endif
  auto parents =
      lock_directories(expected.substr(0, expected.find_last_of(L'\\')));
  auto binary = open_file(expected);
  ServiceHandle manager(OpenSCManagerW(
      nullptr, nullptr, SC_MANAGER_ENUMERATE_SERVICE | SC_MANAGER_CONNECT));
  need(manager.value != nullptr, SD_FLEET_SERVICE);
  DWORD bytes = 0, count = 0, resume = 0;
  EnumServicesStatusExW(manager.value, SC_ENUM_PROCESS_INFO, SERVICE_WIN32,
                        SERVICE_STATE_ALL, nullptr, 0, &bytes, &count, &resume,
                        nullptr);
  need(bytes > 0 && bytes <= 4 * 1024 * 1024, SD_FLEET_SERVICE);
  std::vector<uint8_t> data(bytes);
  resume = 0;
  need(EnumServicesStatusExW(manager.value, SC_ENUM_PROCESS_INFO, SERVICE_WIN32,
                             SERVICE_STATE_ALL, data.data(), DWORD(data.size()),
                             &bytes, &count, &resume, nullptr) != 0,
       SD_FLEET_SERVICE);
  auto rows = reinterpret_cast<ENUM_SERVICE_STATUS_PROCESSW *>(data.data());
  unsigned matches = 0;
  for (DWORD i = 0; i < count; i++) {
    try {
      auto found =
          service(manager.value, rows[i].lpServiceName, expected, false);
      (void)found;
      matches++;
    } catch (const Failure &) {
    }
  }
  need(matches == 1, SD_FLEET_SERVICE);
}
void worker_owned(const ServiceState &state) {
  uint64_t created = 0;
  need(same_path(process_path(GetCurrentProcessId(), &created),
                 install_path()) &&
           created >= state.created,
       SD_FLEET_SERVICE);
  Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
  need(snapshot.value != INVALID_HANDLE_VALUE, SD_FLEET_SERVICE);
  PROCESSENTRY32W entry{};
  entry.dwSize = sizeof(entry);
  need(Process32FirstW(snapshot.value, &entry) != 0, SD_FLEET_SERVICE);
  bool found = false;
  do {
    if (entry.th32ProcessID == GetCurrentProcessId()) {
      need(entry.th32ParentProcessID == state.pid, SD_FLEET_SERVICE);
      found = true;
      break;
    }
  } while (Process32NextW(snapshot.value, &entry));
  need(found, SD_FLEET_SERVICE);
}
std::wstring leaf(const uint16_t *raw) {
  need(raw != nullptr, SD_FLEET_ARGUMENT);
  size_t length = 0;
  while (length <= 128 && raw[length])
    length++;
  need(length > 4 && length <= 128, SD_FLEET_ARGUMENT);
  std::wstring s(reinterpret_cast<const wchar_t *>(raw), length);
  const int kind = sd_fleet_policy::artifact_kind(s);
  need(kind != 0, SD_FLEET_PATH);
  if (kind == 2)
    throw Failure{SD_FLEET_MSI_NOT_APPROVED};
  return s;
}
uint32_t caught() {
  try {
    throw;
  } catch (const Failure &f) {
    return f.status;
  } catch (...) {
    return SD_FLEET_ARGUMENT;
  }
}
} // namespace

struct SdFleetLease {
  std::vector<Handle> directories;
  Handle artifact;
  std::wstring path;
  SdFleetExpected expected{};
  std::array<uint8_t, 32> payload{};
  bool launched = false;
};
namespace {
uint32_t prepare(const SdFleetExpected *e, SdFleetLease **output, bool test) {
  try {
    need(output, SD_FLEET_ARGUMENT);
    *output = nullptr;
    need(e, SD_FLEET_ARGUMENT);
    need(e->size_bytes > 0 && e->size_bytes <= 1024ULL * 1024 * 1024 &&
             e->version_code > 0 && e->version_code <= 65535 &&
             e->architecture == 1,
         SD_FLEET_ARGUMENT);
    SYSTEM_INFO info{};
    GetNativeSystemInfo(&info);
    need(info.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_AMD64,
         SD_FLEET_PRODUCT);
    auto prepared = std::make_unique<SdFleetLease>();
    prepared->directories = ensure_private();
    prepared->path = staging_path() + L"\\" + leaf(e->artifact_leaf);
    prepared->artifact = open_file(prepared->path);
    uint64_t size = 0;
    auto digest = hash(prepared->artifact.value, &size);
    need(size == e->size_bytes &&
             std::memcmp(digest.data(), e->artifact_sha256, 32) == 0,
         SD_FLEET_HASH);
    auto signer = authenticode(prepared->path, prepared->artifact.value);
    need(std::memcmp(signer.data(), e->signer_cert_sha256, 32) == 0,
         SD_FLEET_TRUST);
    architecture(prepared->artifact.value);
    auto meta = metadata(prepared->path, digest);
    need(meta.build == e->version_code, SD_FLEET_VERSION);
    if (!test) {
      auto state = merchant_service();
      worker_owned(state);
      agent_running();
      auto parents = lock_directories(
          install_path().substr(0, install_path().find_last_of(L'\\')));
      auto current = open_file(install_path());
      auto installed = metadata(install_path(), std::array<uint8_t, 32>{});
      need(installed.build < e->version_code, SD_FLEET_VERSION);
    }
    prepared->expected = *e;
    prepared->expected.artifact_leaf = nullptr;
    prepared->payload = meta.payload;
    *output = prepared.release();
    return SD_FLEET_OK;
  } catch (...) {
    return caught();
  }
}
} // namespace
extern "C" uint32_t sd_fleet_private_directory(uint16_t *output,
                                               size_t capacity) {
  try {
    need(output && capacity > 0, SD_FLEET_ARGUMENT);
    output[0] = 0;
    auto hold = ensure_private();
    auto path = staging_path();
    need(path.size() + 1 <= capacity, SD_FLEET_ARGUMENT);
    std::memcpy(output, path.c_str(), (path.size() + 1) * sizeof(wchar_t));
    return 0;
  } catch (...) {
    return caught();
  }
}
extern "C" uint32_t sd_fleet_prepare(const SdFleetExpected *e,
                                     SdFleetLease **output) {
  return prepare(e, output, false);
}
#ifdef SD_FLEET_TEST_BUILD
extern "C" uint32_t sd_fleet_test_prepare(const SdFleetExpected *e,
                                          SdFleetLease **output) {
  return prepare(e, output, true);
}
#endif
extern "C" uint32_t sd_fleet_payload_digest(const SdFleetLease *lease,
                                            uint8_t output[32]) {
  try {
    need(output, SD_FLEET_ARGUMENT);
    std::memset(output, 0, 32);
    need(lease, SD_FLEET_ARGUMENT);
    std::memcpy(output, lease->payload.data(), 32);
    return 0;
  } catch (...) {
    return caught();
  }
}
extern "C" uint32_t sd_fleet_launch(SdFleetLease *lease,
                                    SdFleetResult *result) {
  try {
    need(result, SD_FLEET_ARGUMENT);
    *result = {};
    need(lease, SD_FLEET_ARGUMENT);
    need(!lease->launched, SD_FLEET_ALREADY_LAUNCHED);
    lease->launched = true;
    // Preparation authenticated the bytes while these no-write/no-delete
    // handles were held. Keep the irreversible boundary cheap so the fresh
    // online permit cannot expire during hashing.
    LARGE_INTEGER size{};
    need(GetFileSizeEx(lease->artifact.value, &size) != 0 &&
             size.QuadPart >= 0 &&
             static_cast<uint64_t>(size.QuadPart) ==
                 lease->expected.size_bytes &&
             same_path(final_path(lease->artifact.value), lease->path),
         SD_FLEET_HASH);
    std::wstring command = L"\"" + lease->path + L"\" --silent-install";
    std::vector<wchar_t> args(command.begin(), command.end());
    args.push_back(0);
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    need(CreateProcessW(lease->path.c_str(), args.data(), nullptr, nullptr,
                        FALSE, CREATE_NO_WINDOW, nullptr,
                        staging_path().c_str(), &startup, &process) != 0,
         SD_FLEET_LAUNCH);
    Handle instance(process.hProcess), thread(process.hThread);
    result->process_id = process.dwProcessId;
    FILETIME created, exit, kernel, user;
    need(GetProcessTimes(instance.value, &created, &exit, &kernel, &user) != 0,
         SD_FLEET_WAIT);
    result->process_created = as_time(created);
    need(WaitForSingleObject(instance.value, 5 * 60 * 1000) == WAIT_OBJECT_0,
         SD_FLEET_WAIT);
    DWORD code = 0;
    need(GetExitCodeProcess(instance.value, &code) != 0, SD_FLEET_WAIT);
    result->exit_code = code;
    return SD_FLEET_OK;
  } catch (...) {
    return caught();
  }
}
extern "C" void sd_fleet_release(SdFleetLease *lease) {
  try {
    delete lease;
  } catch (...) {
  }
}
extern "C" uint32_t sd_fleet_local_gates() {
  try {
    auto state = merchant_service();
    worker_owned(state);
    auto parents = lock_directories(
        install_path().substr(0, install_path().find_last_of(L'\\')));
    auto current = open_file(install_path());
    metadata(install_path(), std::array<uint8_t, 32>{});
    agent_running();
    return 0;
  } catch (...) {
    return caught();
  }
}
extern "C" uint32_t sd_fleet_current_service(SdFleetService *result) {
  try {
    need(result, SD_FLEET_ARGUMENT);
    *result = {};
    auto state = merchant_service();
    auto parents = lock_directories(
        install_path().substr(0, install_path().find_last_of(L'\\')));
    auto file = open_file(install_path());
    auto digest = hash(file.value);
    architecture(file.value);
    auto meta = metadata(install_path(), digest);
    result->version_code = meta.build;
    result->process_id = state.pid;
    result->process_created = state.created;
    result->running = 1;
    std::memcpy(result->binary_sha256, digest.data(), 32);
    return 0;
  } catch (...) {
    return caught();
  }
}
extern "C" uint32_t sd_fleet_readback(const SdFleetExpected *e,
                                      uint32_t prior_pid,
                                      uint64_t prior_created,
                                      SdFleetService *result) {
  try {
    need(result, SD_FLEET_ARGUMENT);
    *result = {};
    need(e && e->version_code > 0 && e->version_code <= 65535 &&
             e->architecture == 1 && prior_pid > 0 && prior_created > 0,
         SD_FLEET_ARGUMENT);
    *result = {};
    auto state = merchant_service();
    need(state.pid != prior_pid || state.created != prior_created,
         SD_FLEET_SERVICE);
    need(state.created >= prior_created, SD_FLEET_SERVICE);
    auto parents = lock_directories(
        install_path().substr(0, install_path().find_last_of(L'\\')));
    auto file = open_file(install_path());
    auto digest = hash(file.value);
    architecture(file.value);
    auto meta = metadata(install_path(), digest);
    need(meta.build == e->version_code, SD_FLEET_VERSION);
    result->version_code = meta.build;
    result->process_id = state.pid;
    result->process_created = state.created;
    result->running = 1;
    std::memcpy(result->binary_sha256, digest.data(), 32);
    std::array<uint8_t, 32> zero{};
    need(std::memcmp(e->payload_sha256, zero.data(), 32) != 0 &&
             std::memcmp(digest.data(), e->payload_sha256, 32) == 0,
         SD_FLEET_PAYLOAD_UNPROVEN);
    agent_running();
    return 0;
  } catch (...) {
    return caught();
  }
}
extern "C" uint32_t sd_fleet_os_version(uint32_t *major) {
  try {
    need(major, SD_FLEET_ARGUMENT);
    *major = 0;
    using Function = LONG(WINAPI *)(PRTL_OSVERSIONINFOW);
    Function function = nullptr;
    auto address =
        GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "RtlGetVersion");
    static_assert(sizeof(function) == sizeof(address));
    std::memcpy(&function, &address, sizeof(function));
    need(function, SD_FLEET_ARGUMENT);
    RTL_OSVERSIONINFOW v{};
    v.dwOSVersionInfoSize = sizeof(v);
    need(function(&v) == 0, SD_FLEET_ARGUMENT);
    *major = v.dwMajorVersion;
    return 0;
  } catch (...) {
    return caught();
  }
}

extern "C" uint32_t sd_fleet_boot_id(uint64_t *output) {
  try {
    need(output, SD_FLEET_ARGUMENT);
    *output = 0;
    using Function = LONG(WINAPI *)(ULONG, PVOID, ULONG, PULONG);
    Function function = nullptr;
    auto address = GetProcAddress(GetModuleHandleW(L"ntdll.dll"),
                                  "NtQuerySystemInformation");
    static_assert(sizeof(function) == sizeof(address));
    std::memcpy(&function, &address, sizeof(function));
    need(function, SD_FLEET_ARGUMENT);
    struct BootEnvironment {
      GUID identifier;
      ULONG firmware;
      ULONGLONG flags;
    };
    BootEnvironment value{};
    ULONG returned = 0;
    need(function(90, &value, sizeof(value), &returned) == 0 &&
             returned >= sizeof(GUID),
         SD_FLEET_ARGUMENT);
    GUID zero{};
    need(std::memcmp(&value.identifier, &zero, sizeof(GUID)) != 0,
         SD_FLEET_ARGUMENT);
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    need(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM,
                                     nullptr, 0) >= 0,
         SD_FLEET_ARGUMENT);
    struct Algorithm {
      BCRYPT_ALG_HANDLE h;
      ~Algorithm() { BCryptCloseAlgorithmProvider(h, 0); }
    } close_algorithm{algorithm};
    BCRYPT_HASH_HANDLE hashing = nullptr;
    need(BCryptCreateHash(algorithm, &hashing, nullptr, 0, nullptr, 0, 0) >= 0,
         SD_FLEET_ARGUMENT);
    struct Hashing {
      BCRYPT_HASH_HANDLE h;
      ~Hashing() { BCryptDestroyHash(h); }
    } close_hash{hashing};
    std::array<uint8_t, 32> digest{};
    need(BCryptHashData(hashing, reinterpret_cast<PUCHAR>(&value.identifier),
                        sizeof(GUID), 0) >= 0 &&
             BCryptFinishHash(hashing, digest.data(), DWORD(digest.size()),
                              0) >= 0,
         SD_FLEET_ARGUMENT);
    uint64_t id = 0;
    std::memcpy(&id, digest.data(), sizeof(id));
    need(id != 0, SD_FLEET_ARGUMENT);
    *output = id;
    return 0;
  } catch (...) {
    return caught();
  }
}
