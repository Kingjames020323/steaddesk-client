// Calls the actual candidate platform ABI. The test-only prepare seam bypasses
// only the existing merchant/service parent gate, never file or trust checks.
#include "fleet_installer.h"
#include <windows.h>
#include <cstdio>
#include <cwchar>
#include <string>
#include <stdexcept>
#include <vector>

static void hex(const wchar_t* value, uint8_t out[32]) {
    if (wcslen(value) != 64) throw std::runtime_error("bad test digest");
    for (int i=0;i<32;++i) {
        auto digit=[](wchar_t c)->unsigned { if(c>=L'0'&&c<=L'9')return c-L'0';if(c>=L'a'&&c<=L'f')return c-L'a'+10;throw std::runtime_error("bad test hex"); };
        out[i]=static_cast<uint8_t>((digit(value[2*i])<<4)|digit(value[2*i+1]));
    }
}
static std::string encoded(const uint8_t value[32]) {
    const char* digits="0123456789abcdef";std::string out;
    for(int i=0;i<32;++i){out.push_back(digits[value[i]>>4]);out.push_back(digits[value[i]&15]);}return out;
}
static unsigned long number(const wchar_t* value) { return std::stoul(value); }
int wmain(int argc,wchar_t** argv) {
    static_assert(sizeof(wchar_t)==2,"Windows UTF16 required");
    try {
        const std::wstring action=argc>1?argv[1]:L"";
        if(action==L"directory") {
            uint16_t path[32768]={};auto status=sd_fleet_private_directory(path,32768);
            wprintf(L"{\"status\":%u,\"directory\":\"",status);
            for(const wchar_t* p=reinterpret_cast<wchar_t*>(path);*p;++p){if(*p==L'\\')putwchar(L'\\');putwchar(*p);}wprintf(L"\"}\n");
            return status==SD_FLEET_OK?0:1;
        }
        if(action==L"current") {
            SdFleetService service={};auto status=sd_fleet_current_service(&service);
            printf("{\"status\":%u,\"version\":%llu,\"pid\":%u,\"created\":%llu,\"sha256\":\"%s\"}\n",status,(unsigned long long)service.version_code,service.process_id,(unsigned long long)service.process_created,encoded(service.binary_sha256).c_str());
            return status==SD_FLEET_OK?0:1;
        }
        if(argc<10)throw std::runtime_error("test arguments required");
        SdFleetExpected e={};e.artifact_leaf=reinterpret_cast<const uint16_t*>(argv[2]);e.size_bytes=std::stoull(argv[3]);e.version_code=std::stoull(argv[4]);e.architecture=1;
        hex(argv[5],e.artifact_sha256);hex(argv[6],e.signer_cert_sha256);hex(argv[7],e.payload_sha256);
        auto expected=number(argv[8]);
        if(action==L"readback") {
            if(argc!=12)throw std::runtime_error("readback arguments required");
            SdFleetService service={};auto status=sd_fleet_readback(&e,number(argv[10]),std::stoull(argv[11]),&service);
            printf("{\"status\":%u,\"expected\":%lu,\"version\":%llu,\"pid\":%u,\"created\":%llu,\"sha256\":\"%s\"}\n",status,expected,(unsigned long long)service.version_code,service.process_id,(unsigned long long)service.process_created,encoded(service.binary_sha256).c_str());
            return status==expected?0:1;
        }
        SdFleetLease* lease=nullptr;
        auto status=sd_fleet_test_prepare(&e,&lease);
        printf("{\"status\":%u,\"expected\":%lu,\"case\":\"prepare\"}\n",status,expected);
        if(status!=expected){if(lease)sd_fleet_release(lease);return 1;}
        if(status!=SD_FLEET_OK)return lease==nullptr?0:1;
        uint8_t payload[32]={};auto payload_status=sd_fleet_payload_digest(lease,payload);
        printf("{\"payload_status\":%u,\"payload_sha256\":\"%s\"}\n",payload_status,encoded(payload).c_str());
        if(payload_status!=0 || encoded(payload)!=encoded(e.payload_sha256)){sd_fleet_release(lease);return 1;}
        if(action==L"launch") {
            uint16_t root[32768]={};sd_fleet_private_directory(root,32768);
            std::wstring target=reinterpret_cast<wchar_t*>(root);target+=L"\\";target+=argv[2];
            HANDLE writer=CreateFileW(target.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);
            if(writer!=INVALID_HANDLE_VALUE){CloseHandle(writer);sd_fleet_release(lease);return 1;}
            auto moved=target+L".renamed";
            if(MoveFileW(target.c_str(),moved.c_str())){sd_fleet_release(lease);return 1;}
            SdFleetResult result={};auto launch=sd_fleet_launch(lease,&result);
            printf("{\"case\":\"launch\",\"status\":%u,\"exit\":%u,\"pid\":%u}\n",launch,result.exit_code,result.process_id);
            SdFleetResult duplicate={};auto twice=sd_fleet_launch(lease,&duplicate);
            printf("{\"case\":\"duplicate_launch\",\"status\":%u}\n",twice);
            sd_fleet_release(lease);
            return launch==0&&result.exit_code==number(argv[9])&&twice==SD_FLEET_ALREADY_LAUNCHED?0:1;
        }
        sd_fleet_release(lease);return 0;
    }catch(const std::exception& error){fprintf(stderr,"test probe: %s\n",error.what());return 2;}
}
