/* Disposable test installer. It never installs a service, agent, password or product.
 * Production code must not compile or ship this test fixture.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

static SERVICE_STATUS_HANDLE status_handle;
static SERVICE_STATUS service_status;
static HANDLE stop_event;
static void WINAPI control(DWORD request) {
    if (request == SERVICE_CONTROL_STOP) {
        service_status.dwCurrentState = SERVICE_STOP_PENDING;
        SetServiceStatus(status_handle, &service_status);
        SetEvent(stop_event);
    }
}
static void WINAPI service_main(DWORD argc, LPWSTR *argv) {
    (void)argc;
    status_handle = RegisterServiceCtrlHandlerW(argv[0], control);
    if (status_handle == NULL) return;
    stop_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    ZeroMemory(&service_status, sizeof(service_status));
    service_status.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    service_status.dwCurrentState = SERVICE_RUNNING;
    service_status.dwControlsAccepted = SERVICE_ACCEPT_STOP;
    SetServiceStatus(status_handle, &service_status);
    WaitForSingleObject(stop_event, INFINITE);
    service_status.dwCurrentState = SERVICE_STOPPED;
    SetServiceStatus(status_handle, &service_status);
    CloseHandle(stop_event);
}

int main(int argc, char **argv) {
    const char *raw_code;
    const char *receipt;
    char *end;
    long code;
    FILE *out;
    if (argc == 2 && (strcmp(argv[1], "--server") == 0 || strcmp(argv[1], "--service") == 0)) {
        SERVICE_TABLE_ENTRYW table[] = {{L"SteadDeskFleetTest", service_main}, {NULL, NULL}};
        return StartServiceCtrlDispatcherW(table) ? 0 : 69;
    }
    if (argc != 2 || strcmp(argv[1], "--silent-install") != 0) return 64;
    raw_code = getenv("SD_UPD4_FIXTURE_EXIT");
    receipt = getenv("SD_UPD4_FIXTURE_RECEIPT");
    if (raw_code == NULL || receipt == NULL || receipt[0] == '\0') return 65;
    code = strtol(raw_code, &end, 10);
    if (*end != '\0' || (code != 0 && code != 3010 && code != 1603)) return 66;
    out = fopen(receipt, "ab");
    if (out == NULL) return 67;
    fprintf(out, "{\"fixture\":\"SDUPD4\",\"reviewed_argument\":\"--silent-install\",\"exit\":%ld}\n", code);
    if (fclose(out) != 0) return 68;
    return (int)code;
}
